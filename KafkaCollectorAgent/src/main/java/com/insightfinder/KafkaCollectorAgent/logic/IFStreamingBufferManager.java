package com.insightfinder.KafkaCollectorAgent.logic;

import com.google.common.hash.BloomFilter;
import com.google.common.hash.Funnels;
import com.google.gson.Gson;
import com.google.gson.JsonObject;
import com.google.gson.reflect.TypeToken;
import com.insightfinder.KafkaCollectorAgent.logic.config.IFConfig;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.client.HttpServerErrorException;
import org.springframework.web.reactive.function.BodyInserters;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;
import javax.annotation.PostConstruct;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Type;
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.*;
import java.util.logging.Level;
import java.util.logging.Logger;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

@Component
public class IFStreamingBufferManager {
    private Logger logger = Logger.getLogger(IFStreamingBufferManager.class.getName());
    public static Type MAP_MAP_TYPE = new TypeToken<Map<String, Map<String, String>>>() {}.getType();

    @Autowired
    private Gson gson;
    @Autowired
    private IFConfig ifConfig;
    @Autowired
    private IFProjectManager projectManager;
    @Autowired
    private WebClient webClient;
    private boolean isJSON;
    private Pattern dataFormatPattern;
    private Map<String, Integer> namedGroups;
    private Map<String, Map<String, String>> projectList;
    private Set<String> instanceList;
    private Pattern metricPattern;
    private ExecutorService executorService = Executors.newFixedThreadPool(5);
    private Map<Long, ThreadBuffer> threadBufferMap = new HashMap<>();
    private ConcurrentHashMap<String, Set<IFStreamingBuffer>> collectingDataMap = new ConcurrentHashMap<>();
    private ConcurrentHashMap<String, Set<IFStreamingBuffer>> collectedBufferMap = new ConcurrentHashMap<>();
    private Queue<IFSendingBuffer> retryQueue = new LinkedBlockingQueue<>();
    BloomFilter<String> filter = BloomFilter.create(
            Funnels.stringFunnel(Charset.defaultCharset()),
            100000000);
    public IFStreamingBufferManager() {
    }

    @PostConstruct
    public void init() throws InvocationTargetException, NoSuchMethodException, IllegalAccessException {
        if (ifConfig.getDataFormat().equalsIgnoreCase("JSON")){
            isJSON = true;
            dataFormatPattern = null;
        }else {
            isJSON = false;
            if (ifConfig.getDataFormatRegex() != null){
                dataFormatPattern = Pattern.compile(ifConfig.getDataFormatRegex());
                namedGroups = getNamedGroups(dataFormatPattern);
            }
        }

        if (ifConfig.getMetricRegex() != null){
            metricPattern = Pattern.compile(ifConfig.getMetricRegex());
        }

        projectList = getProjectMapping(ifConfig.getProjectList());
        instanceList = ifConfig.getInstanceList();
        //timer thread
        executorService.execute(()->{
            int collectingTimer = ifConfig.getCollectingTime();
            int sentTimer = ifConfig.getSamplingIntervalInSeconds();
            while (true){
                if (collectingTimer <= 0){
                    collectingTimer = ifConfig.getCollectingTime();
                    //collecting data thread
                    executorService.execute(()->{
                        long timestamp = System.currentTimeMillis() - ifConfig.getCollectingTime()*1000;
                        threadBufferMap.entrySet().forEach(entry -> {
                            entry.getValue().poll(collectingDataMap, timestamp);
                        });
                    });
                }
                if (sentTimer <= 0){
                    sentTimer = ifConfig.getSamplingIntervalInSeconds();
                    //sending data thread
                    executorService.execute(()->{
                        mergeDataAndSendToIF(collectingDataMap);
                    });
                }

                try {
                    Thread.sleep(1000);
                    collectingTimer--;
                    sentTimer--;
                } catch (InterruptedException e) {
                    throw new RuntimeException(e);
                }
            }
        });
    }
    public Map<String, Map<String, String>> getProjectMapping(String projectList){
        Map<String, Map<String, String>> mapping = new HashMap<>();
        mapping = gson.fromJson(projectList, MAP_MAP_TYPE);

        Map<String, Map<String, String>> resultMapping = new HashMap<>();
        for (String projectKey : mapping.keySet()){
            String[] keys = projectKey.split(ifConfig.getProjectDelimiter());
            for (String key : keys){
                resultMapping.put(key, mapping.get(key));
            }
        }

        return resultMapping;
    }



    synchronized public void addThreadBuffer(long threadId){
        if (!threadBufferMap.containsKey(threadId)){
            threadBufferMap.put(threadId, new ThreadBuffer());
        }
    }

    public void parseString(String content, long receiveTime){
        JsonObject jsonObject = null;
        if (isJSON){
            //to do
        }else {
            if (content.startsWith("\"") && content.endsWith("\"")){
                content = content.substring(1, content.length() - 1);
            }
            Matcher matcher = dataFormatPattern.matcher(content.trim());
            if (matcher.matches() && namedGroups != null){
                List<String> projects = new ArrayList<>();
                jsonObject = new JsonObject();
                String projectNameStr = null, instanceName = null, timeStamp = null;
                for (String key : namedGroups.keySet()){
                    if (key.equalsIgnoreCase(ifConfig.getProjectKey())){
                        projectNameStr = String.valueOf(matcher.group(key));
                        String[] projectNames = projectNameStr.split(ifConfig.getProjectDelimiter());
                        for (String projectName : projectNames){
                            if (!projectList.keySet().contains(projectName)){
                                if (ifConfig.isLogParsingInfo()) {
                                    logger.log(Level.INFO, projectName + " not in the projectList ");
                                }
                            }else {
                                projects.add(projectName);
                            }
                        }

                    } else if (key.equalsIgnoreCase(ifConfig.getInstanceKey())){
                        instanceName = String.valueOf(matcher.group(key));
                        if (!instanceList.contains(instanceName)){
                            if (ifConfig.isLogParsingInfo()) {
                                logger.log(Level.INFO, instanceName + " not in the instanceList ");
                            }
                            return;
                        }
                    } else if (key.equalsIgnoreCase(ifConfig.getTimestampKey())){
                        timeStamp = convertToMS(matcher.group(key));
                    }else if (key.equalsIgnoreCase(ifConfig.getMetricKey())){
                        Matcher metricMatcher = metricPattern.matcher(matcher.group(key));
                        if (metricMatcher.matches()){
                            jsonObject.addProperty(matcher.group(key), matcher.group(ifConfig.getValueKey()));
                        }else {
                            if (ifConfig.isLogParsingInfo()) {
                                logger.log(Level.INFO, "Not match the metric regex " + content);
                            }
                            return;
                        }
                    }
                }
                if (projects.size() > 0 && instanceName != null && timeStamp != null){
                    if (ifConfig.isLogParsingInfo()) {
                        logger.log(Level.INFO, "Parse success " + content);
                    }
                    ThreadBuffer threadBuffer = threadBufferMap.get(Thread.currentThread().getId());
                    if (threadBuffer != null){
                        for (String projectName : projects){
                            threadBuffer.addBuffer(projectName, instanceName, timeStamp, jsonObject, receiveTime);
                        }
                    }
                }
            }else {
                if (ifConfig.isLogParsingInfo()){
                    logger.log(Level.INFO, " Parse failed, not match the regex " + content);
                }
            }
        }
    }

    public String convertToMS(String timestamp){
        StringBuilder stringBuilder = new StringBuilder();
        stringBuilder.append(timestamp);
        if (stringBuilder.length() == 10){
            stringBuilder.append("000");
        }
        return stringBuilder.toString();
    }

    public void mergeDataAndSendToIF(Map<String, Set<IFStreamingBuffer>> collectingDataMap){
        Map<String, IFSendingBuffer> sendingBufferMap = new HashMap<>();
        synchronized (collectedBufferMap){
            for (String key : collectedBufferMap.keySet()){
                if (!collectingDataMap.keySet().contains(key)){
                    if (filter.mightContain(key)){
                        if (ifConfig.isLogSendingData()) {
                            StringBuilder stringBuilder = new StringBuilder();
                            collectedBufferMap.get(key).forEach(ifStreamingBuffer -> {
                                stringBuilder.append(ifStreamingBuffer.getData().toString()).append("\n");
                            });
                            logger.log(Level.INFO, key + " data: " + stringBuilder.toString());
                        }
                        continue;
                    }
                    filter.put(key);
                    IFStreamingBuffer ifStreamingBuffer = merge(collectedBufferMap.get(key));
                    if (!sendingBufferMap.containsKey(ifStreamingBuffer.getProject())){
                        sendingBufferMap.put(ifStreamingBuffer.getProject(), new IFSendingBuffer(ifStreamingBuffer));
                    }else {
                        sendingBufferMap.get(ifStreamingBuffer.getProject()).addData(ifStreamingBuffer);
                    }
                    collectedBufferMap.remove(key);
                }
            }

            synchronized (collectingDataMap){
                for(String key : collectingDataMap.keySet()){
                    if (!collectedBufferMap.contains(key)){
                        collectedBufferMap.put(key, ConcurrentHashMap.newKeySet());
                    }
                    collectedBufferMap.get(key).addAll(collectingDataMap.get(key));
                }
                collectingDataMap.clear();
            }
        }

        while (!retryQueue.isEmpty()){
            IFSendingBuffer ifSendingBuffer = retryQueue.poll();
            sendToIF(ifSendingBuffer.getJsonObjectList(), ifSendingBuffer.getProject(), 3);
        }

        for (IFSendingBuffer ifSendingBuffer : sendingBufferMap.values()){
            sendToIF(ifSendingBuffer.getJsonObjectList(), ifSendingBuffer.getProject(), 0);
        }
    }

    public void sendToIF(List<JsonObject> list, String projectName, int retry){
        Map<String, String> ifProjectInfo = projectList.get(projectName);
        String ifProjectName = ifProjectInfo.get("project");
        String ifSystemName = ifProjectInfo.get("system");
        if (projectManager.checkAndCreateProject(ifProjectName, ifSystemName)){
            UUID uuid = UUID.randomUUID();
            MultiValueMap<String, String> bodyValues = new LinkedMultiValueMap<>();
            bodyValues.add("licenseKey", ifConfig.getLicenseKey());
            bodyValues.add("projectName", ifProjectName);
            bodyValues.add("userName", ifConfig.getUserName());
            bodyValues.add("metricData", new Gson().toJson(list));
            bodyValues.add("agentType", ifConfig.getAgentType());
            webClient.post()
                    .uri(ifConfig.getServerUri())
                    .header(HttpHeaders.CONTENT_TYPE, MediaType.APPLICATION_JSON_VALUE)
                    .body(BodyInserters.fromFormData(bodyValues))
                    .retrieve()
                    .bodyToMono(String.class)
                    .timeout(Duration.ofMillis(20000))
                    .onErrorResume(throwable -> {
                        return Mono.just("RETRY");
                    })
                    .subscribe(res->{
                        if (res.equalsIgnoreCase("RETRY") && retry < 2){//retry 1 2
                            sendToIF(list.subList(0, list.size()/2), projectName, retry + 1);
                            sendToIF(list.subList(list.size()/2, list.size()), projectName, retry + 1);
                        }else {
                            if (res.equalsIgnoreCase("RETRY") && retry == 2){// retry 3
                                retryQueue.add(new IFSendingBuffer(projectName, list));
                            }else {
                                logger.log(Level.INFO,  "request id: " + uuid.toString() + " " + res);
                            }
                        }
                    });
        }
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Integer> getNamedGroups(Pattern regex)
            throws NoSuchMethodException, SecurityException,
            IllegalAccessException, IllegalArgumentException,
            InvocationTargetException {

        Method namedGroupsMethod = Pattern.class.getDeclaredMethod("namedGroups");
        namedGroupsMethod.setAccessible(true);

        Map<String, Integer> namedGroups = null;
        namedGroups = (Map<String, Integer>) namedGroupsMethod.invoke(regex);

        if (namedGroups == null) {
            throw new InternalError();
        }

        return Collections.unmodifiableMap(namedGroups);
    }

    public static IFStreamingBuffer merge(Collection<IFStreamingBuffer> collection){
        return collection.stream().reduce((ib1, ib2)->{
            return ib1.merge(ib2);
        }).get();
    }
}
