package com.insightfinder.KafkaCollectorAgent.logic;

import com.google.common.hash.BloomFilter;
import com.google.common.hash.Funnels;
import com.google.gson.Gson;
import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import com.google.gson.reflect.TypeToken;
import com.insightfinder.KafkaCollectorAgent.logic.config.IFConfig;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.reactive.function.BodyInserters;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

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
    private static Set<String> metricFilterSet = new HashSet<>();
    static {
        metricFilterSet.add("kafka.consumer.fetch.manager.records.lag");
        metricFilterSet.add("kafka.consumer.fetch.manager.records.lag.max");
        metricFilterSet.add("kafka.consumer.fetch.manager.bytes.consumed.rate");
        metricFilterSet.add("kafka.consumer.fetch.manager.records.consumed.rate");
        metricFilterSet.add("kafka.consumer.fetch.manager.fetch.rate");
    }

    private Logger logger = Logger.getLogger(IFStreamingBufferManager.class.getName());
    public static Type MAP_MAP_TYPE = new TypeToken<Map<String, Map<String, String>>>() {}.getType();
    @Autowired
    private MeterRegistry registry;
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
    private final ConcurrentHashMap<String, IFStreamingBuffer> collectingDataMap = new ConcurrentHashMap<>();
    private final ConcurrentHashMap<String, IFStreamingBuffer> collectedBufferMap = new ConcurrentHashMap<>();
    private final ConcurrentHashMap<String, Integer> sendingStatistics = new ConcurrentHashMap<>();
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
            int printMetricsTimer = 3600;
            int sentTimer = ifConfig.getBufferingTime();
            while (true){
                if (sentTimer <= 0){
                    sentTimer = ifConfig.getBufferingTime();
                    //sending data thread
                    executorService.execute(()->{
                        mergeDataAndSendToIF2(collectingDataMap);
                    });
                }

                if (printMetricsTimer <= 0){
                    printMetricsTimer = 3600;
                    registry.getMeters().forEach(meter -> {
                        if (metricFilterSet.contains(meter.getId().getName())){
                            meter.measure().forEach(measurement -> {
                                logger.log(Level.INFO, String.format("%s %s : %f",meter.getId().getTag("client.id"), meter.getId().getName(), measurement.getValue()));
                            });
                        }
                    });
                }

                try {
                    Thread.sleep(1000);
                    printMetricsTimer--;
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
                resultMapping.put(key, mapping.get(projectKey));
            }
        }

        return resultMapping;
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
                String projectNameStr = null, instanceName = null, timeStamp = null, metricName = null;
                double metricValue = 0.0;
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
                            metricName = matcher.group(key);
                            metricValue = Double.parseDouble(matcher.group(ifConfig.getValueKey()));
                        }else {
                            if (ifConfig.isLogParsingInfo()) {
                                logger.log(Level.INFO, "Not match the metric regex " + content);
                            }
                            return;
                        }
                    }
                }
                if (projects.size() > 0 && instanceName != null && metricName != null && timeStamp != null){
                    if (ifConfig.isLogParsingInfo()) {
                        logger.log(Level.INFO, "Parse success " + content);
                    }

                    if (ifConfig.getMetricNameFilter() != null &&  ifConfig.getMetricNameFilter().equalsIgnoreCase(metricName)){
                        logger.log(Level.INFO, String.format("%s %s %s", instanceName, metricName, timeStamp));
                    }

                    for (String projectName : projects){
                        long start = System.currentTimeMillis();
                        Map<String, String> ifProjectInfo = projectList.get(projectName);
                        String ifProjectName = ifProjectInfo.get("project");
                        String ifSystemName = ifProjectInfo.get("system");
                        if (!collectingDataMap.containsKey(ifProjectName)){
                            collectingDataMap.put(ifProjectName, new IFStreamingBuffer(ifProjectName, ifSystemName));
                        }
                        collectingDataMap.get(ifProjectName).addData(instanceName, Long.parseLong(timeStamp), metricName, metricValue);
                        long end = System.currentTimeMillis();
                        if (end - start > 1000){
                            logger.log(Level.INFO, "add use " + ((end - start)/1000) + " size"+ collectingDataMap.size());
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

    public void mergeDataAndSendToIF2(Map<String, IFStreamingBuffer> collectingDataMap){
        List<IFStreamingBuffer> sendingDataList = new ArrayList<>();
        for (String key : collectedBufferMap.keySet()){
            if (collectingDataMap.containsKey(key)){
                IFStreamingBuffer ifStreamingBuffer = collectedBufferMap.get(key).mergeDataAndGetSendingData(collectingDataMap.get(key));
                sendingDataList.add(ifStreamingBuffer);
            }else {
                IFStreamingBuffer ifStreamingBuffer = collectedBufferMap.remove(key);
                sendingDataList.add(ifStreamingBuffer);
            }
        }

        for (String key : collectingDataMap.keySet()){
            if (!collectedBufferMap.containsKey(key)){
                collectedBufferMap.put(key, collectingDataMap.remove(key));
            }
        }

        for (IFStreamingBuffer ifSendingBuffer : sendingDataList){
            convertBackToOldFormat(ifSendingBuffer.getAllInstanceDataMap(), ifSendingBuffer.getProject(), ifSendingBuffer.getSystem(), 10000);
        }
    }

    public void convertBackToOldFormat(Map<String, InstanceData> instanceDataMap, String project, String system,int splitNum) {
        List<String> stringList = new ArrayList<>();
        List<Map<Long, JsonObject>> sortByTimestampMaps = new ArrayList<>();
        Map<Long, JsonObject> sortByTimestampMap = new HashMap<>();
        int total = splitNum;
        for (String instanceName : instanceDataMap.keySet()) {
            InstanceData instanceData = instanceDataMap.get(instanceName);
            Map<Long, DataInTimestamp> dataInTimestampMap = instanceData.getDataInTimestampMap();
            for (Long timestamp : dataInTimestampMap.keySet()) {
                String key = String.format("%s-%s-%d", project, instanceName, timestamp);
                if (filter.mightContain(key)){
                    if (ifConfig.isLogSendingData()) {
                        if (sendingStatistics.containsKey(key)){
                                float percent = dataInTimestampMap.get(timestamp).getMetricDataPointSet().size() / sendingStatistics.get(key);
                                String dropStr = String.format("At %s drop data / sent data: %f", key, percent*100);
                                logger.log(Level.INFO, dropStr);
                        }else {
                                String dropStr = String.format("At %s drop data %d", key,dataInTimestampMap.get(timestamp).getMetricDataPointSet().size());
                                logger.log(Level.INFO, dropStr);
                        }
                    }
                    continue;
                }
                filter.put(key);
                if (ifConfig.isLogSendingData()) {
                        sendingStatistics.put(key, dataInTimestampMap.get(timestamp).getMetricDataPointSet().size());
                }

                JsonObject thisTimestampObj = sortByTimestampMap.getOrDefault(timestamp, new JsonObject());
                if (!thisTimestampObj.has("timestamp")) {
                    thisTimestampObj.addProperty("timestamp", timestamp.toString());
                }
                Set<MetricDataPoint> metricDataPointSet = dataInTimestampMap.get(timestamp)
                        .getMetricDataPointSet();
                if (total - metricDataPointSet.size() < 0){
                    total = splitNum;
                    if (!sortByTimestampMap.isEmpty()){
                        sendToIF(sortByTimestampMap, project, system);
                        sortByTimestampMap = new HashMap<>();
                    }
                }
                for (MetricDataPoint metricDataPoint : metricDataPointSet) {
                    String metricName = metricDataPoint.getMetricName();
                    double value = metricDataPoint.getValue();
                    MetricHeaderEntity metricHeaderEntity = new MetricHeaderEntity(metricName, instanceName,
                            null);
                    String header = metricHeaderEntity.generateHeader(false);
                    thisTimestampObj.addProperty(header, String.valueOf(value));
                }
                total -= metricDataPointSet.size();
                sortByTimestampMap.put(timestamp, thisTimestampObj);
            }
        }
        if (!sortByTimestampMap.isEmpty()){
            sendToIF(sortByTimestampMap, project, system);
        }
    }

    public void sendToIF(Map<Long, JsonObject> sortByTimestampMap, String project, String system){
        JsonArray ret = new JsonArray();
        for (JsonObject jsonObject : sortByTimestampMap.values()) {
            ret.add(jsonObject);
        }
        sendToIF(ret.toString(), project, system);
    }

    public void sendToIF(String data, String ifProjectName, String ifSystemName){

        if (projectManager.checkAndCreateProject(ifProjectName, ifSystemName)){
            UUID uuid = UUID.randomUUID();
            MultiValueMap<String, String> bodyValues = new LinkedMultiValueMap<>();
            bodyValues.add("licenseKey", ifConfig.getLicenseKey());
            bodyValues.add("projectName", ifProjectName);
            bodyValues.add("userName", ifConfig.getUserName());
            bodyValues.add("metricData", data);
            bodyValues.add("agentType", ifConfig.getAgentType());
            int dataSize = data.getBytes(StandardCharsets.UTF_8).length/1024;
            webClient.post()
                    .uri(ifConfig.getServerUri())
                    .header(HttpHeaders.CONTENT_TYPE, MediaType.APPLICATION_JSON_VALUE)
                    .body(BodyInserters.fromFormData(bodyValues))
                    .retrieve()
                    .bodyToMono(String.class)
                    .timeout(Duration.ofMillis(100000))
                    .onErrorResume(throwable -> {
                        return Mono.just("RETRY");
                    })
                    .subscribe(res->{
                        if (res.equalsIgnoreCase("RETRY")){//retry 1 2
                            logger.log(Level.INFO,  "request id: " + uuid.toString() + " data size: " +  dataSize + " kb code: "+res);
                        }else {
                            logger.log(Level.INFO,  "request id: " + uuid.toString() + " data size: " +  dataSize + " kb code: "+res);
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

}
