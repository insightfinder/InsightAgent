package com.insightfinder.KafkaCollectorAgent.logic;

import com.google.common.collect.Lists;
import com.google.common.hash.BloomFilter;
import com.google.common.hash.Funnels;
import com.google.gson.Gson;
import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import com.google.gson.reflect.TypeToken;
import com.insightfinder.KafkaCollectorAgent.logic.config.IFConfig;
import io.micrometer.core.instrument.MeterRegistry;
import org.apache.kafka.common.protocol.types.Field;
import org.springframework.beans.factory.annotation.Autowired;
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
import java.text.ParseException;
import java.text.SimpleDateFormat;
import java.time.Duration;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.logging.Level;
import java.util.logging.Logger;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

@Component
public class IFStreamingBufferManager {
    public static Type MAP_MAP_TYPE = new TypeToken<Map<String, Map<String, String>>>() {
    }.getType();
    private static final Set<String> metricFilterSet = new HashSet<>();

    static {
        metricFilterSet.add("kafka.consumer.fetch.manager.records.lag");
        metricFilterSet.add("kafka.consumer.fetch.manager.records.lag.max");
        metricFilterSet.add("kafka.consumer.fetch.manager.bytes.consumed.rate");
        metricFilterSet.add("kafka.consumer.fetch.manager.records.consumed.rate");
        metricFilterSet.add("kafka.consumer.fetch.manager.fetch.rate");
    }

    private final ConcurrentHashMap<String, IFStreamingBuffer> collectingDataMap = new ConcurrentHashMap<>();
    private final ConcurrentHashMap<String, Set<JsonObject>> collectingLogDataMap = new ConcurrentHashMap<>();
    private final ConcurrentHashMap<String, Set<JsonObject>> collectingLogMetadataMap = new ConcurrentHashMap<>();
    private final ConcurrentHashMap<String, IFStreamingBuffer> collectedBufferMap = new ConcurrentHashMap<>();
    private final ConcurrentHashMap<String, Integer> sendingStatistics = new ConcurrentHashMap<>();
    private final ConcurrentHashMap<String, Long> sendingTimeStatistics = new ConcurrentHashMap<>();
    BloomFilter<String> filter = BloomFilter.create(
            Funnels.stringFunnel(Charset.defaultCharset()),
            100000000);
    private final Logger logger = Logger.getLogger(IFStreamingBufferManager.class.getName());
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
    private final ExecutorService executorService = Executors.newFixedThreadPool(5);

    public IFStreamingBufferManager() {
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



    public void setFilter(BloomFilter<String> filter) {
        this.filter = filter;
    }

    public void setGson(Gson gson) {
        this.gson = gson;
    }

    public void setIfConfig(IFConfig ifConfig) {
        this.ifConfig = ifConfig;
    }

    public void setProjectManager(IFProjectManager projectManager) {
        this.projectManager = projectManager;
    }

    public void setWebClient(WebClient webClient) {
        this.webClient = webClient;
    }

    public void setProjectList(Map<String, Map<String, String>> projectList) {
        this.projectList = projectList;
    }

    @PostConstruct
    public void init() throws InvocationTargetException, NoSuchMethodException, IllegalAccessException {
        if (ifConfig.getDataFormat().equalsIgnoreCase("JSON")) {
            isJSON = true;
            dataFormatPattern = null;
        } else {
            isJSON = false;
            if (ifConfig.getDataFormatRegex() != null) {
                dataFormatPattern = Pattern.compile(ifConfig.getDataFormatRegex());
                namedGroups = getNamedGroups(dataFormatPattern);
            }
        }

        if (ifConfig.getMetricRegex() != null) {
            metricPattern = Pattern.compile(ifConfig.getMetricRegex());
        }
        if (ifConfig.getProjectList() != null) {
            projectList = getProjectMapping(ifConfig.getProjectList());
        }

        instanceList = ifConfig.getInstanceList();
        //timer thread
        executorService.execute(() -> {
            int printMetricsTimer = ifConfig.getKafkaMetricLogInterval();
            int sentTimer = ifConfig.getBufferingTime();
            while (true) {
                if (sentTimer <= 0) {
                    sentTimer = ifConfig.getBufferingTime();
                    //sending data thread
                    executorService.execute(() -> {
                        if (ifConfig.isLogProject()) {
                            mergeLogDataAndSendToIF2(collectingLogDataMap);
                        } else {
                            mergeDataAndSendToIF2(collectingDataMap);
                        }
                    });
                }

                if (printMetricsTimer <= 0) {
                    printMetricsTimer = ifConfig.getKafkaMetricLogInterval();
                    registry.getMeters().forEach(meter -> {
                        if (metricFilterSet.contains(meter.getId().getName())) {
                            meter.measure().forEach(measurement -> {
                                logger.log(Level.INFO, String.format("%s %s : %f", meter.getId().getTag("client.id"), meter.getId().getName(), measurement.getValue()));
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

    public Map<String, Map<String, String>> getProjectMapping(String projectList) {
        Map<String, Map<String, String>> mapping = new HashMap<>();
        mapping = gson.fromJson(projectList, MAP_MAP_TYPE);
        Map<String, Map<String, String>> resultMapping = new HashMap<>();
        for (String projectKey : mapping.keySet()) {
            String[] keys = projectKey.split(ifConfig.getProjectDelimiter());
            for (String key : keys) {
                resultMapping.put(key, mapping.get(projectKey));
            }
        }

        return resultMapping;
    }

    public long getGMTinHourFromMillis(String date, String format) {
        //"yyyy-MM-dd'T'HH:mm:ssZZZZZ"
        DateTimeFormatter rfc3339Formatter = DateTimeFormatter.ofPattern(format)
                .withResolverStyle(ResolverStyle.LENIENT);
        ZonedDateTime zonedDateTime = parseRfc3339(date, rfc3339Formatter);
        if (zonedDateTime != null){
            return zonedDateTime.toInstant().toEpochMilli();
        }
        return -1;
    }

    public  ZonedDateTime parseRfc3339(String rfcDateTime, DateTimeFormatter rfc3339Formatter) {
        try {
            return ZonedDateTime.parse(rfcDateTime, rfc3339Formatter);
        }catch (DateTimeParseException exception){
            logger.log(Level.INFO, " can not pare date :" + rfcDateTime);
        }
        return null;
    }

    private JsonObject processMetadata(JsonObject srcData){
        JsonObject data = new JsonObject();
        String instanceStr = getKeyFromJson(srcData, ifConfig.getLogInstanceFieldPathList());
        if (instanceStr == null) {
            if (ifConfig.isLogParsingInfo()) {
                logger.log(Level.INFO, " can not find instance in raw data:" + srcData);
            }
            return null;
        }
        data.addProperty("instanceName", instanceStr);
        List<List<String>> logComponentList = getLogComponentList();
        if (logComponentList != null && !logComponentList.isEmpty()){
            String componentName = getComponentName(srcData, logComponentList);
            if (componentName != null){
                data.addProperty("componentName", componentName);
            }
        }
        return data;
    }

    private String getIFProjectAndSystemInfo(JsonObject srcData){
        String ret = null;
        for (String keyStr : projectList.keySet()){
            String[] keysArr = keyStr.split(",");
            boolean bMatch = true;
            for (String key : keysArr){
                String[] keyArr = key.split(":");
                if (keyArr.length == 2 && srcData.has(keyArr[0]) && srcData.get(keyArr[0]).getAsString().equalsIgnoreCase(keyArr[1])){
                    bMatch = bMatch && true;
                }else if (keyArr .length == 1 && srcData.has(keyArr[0])){
                    bMatch = bMatch && true;
                }else {
                    bMatch = false;
                }
            }

            if (bMatch){
                return String.format("%s@%s",projectList.get(keyStr).get("project"), projectList.get(keyStr).get("system")) ;
            }
        }
        return  ret;
    }

    private JsonObject processLogData(JsonObject srcData) {
        JsonObject data = new JsonObject();
        String timestampStr = getKeyFromJson(srcData, ifConfig.getLogTimestampFieldPathList());
        if (timestampStr == null) {
            if (ifConfig.isLogParsingInfo()) {
                logger.log(Level.INFO, " can not find timestamp in raw data: " + srcData);
            }
            return null;
        }
        Long timestamp = getGMTinHourFromMillis(timestampStr, ifConfig.getLogTimestampFormat());
        if (timestamp < 0) {
            if (ifConfig.isLogParsingInfo()) {
                logger.log(Level.INFO, " can not parse timestamp from raw data: " + srcData);
            }
            return null;
        }
        String instanceStr = getKeyFromJson(srcData, ifConfig.getLogInstanceFieldPathList());
        if (instanceStr == null) {
            if (ifConfig.isLogParsingInfo()) {
                logger.log(Level.INFO, " can not find instance in raw data:" + srcData);
            }
            return null;
        }

        data.addProperty("timestamp", timestamp.toString());
        data.addProperty("tag", instanceStr);
        data.add("data", srcData);
        return data;
    }

    private String getComponentName(JsonObject srcData, List<List<String>> logComponentList){
        String componentName = null;
        if (logComponentList != null){
            List<String> subComponents = new ArrayList<>();
            for (int i = 0; i < logComponentList.size(); i++){
                List<String> componentPaths = logComponentList.get(i);
                componentPaths.forEach(componentPath -> {
                    String value = getKeyFromJson(srcData, Arrays.asList(componentPath));
                    if (value != null){
                        subComponents.add(value);
                    }
                });
                if (subComponents.size() == componentPaths.size()){
                    componentName = String.join("-", subComponents);
                    return componentName;
                }else {
                    subComponents.clear();
                    continue;
                }
            }

        }
        return componentName;
    }

    private List<List<String>> getLogComponentList(){
        List<String> logComponentFieldPathList = ifConfig.getLogComponentFieldPathList();
        List<List<String>> ans = new ArrayList<>();
        if (logComponentFieldPathList != null){
            logComponentFieldPathList.forEach(pathStr->{
                List<String> pathList = Arrays.asList(pathStr.split("&"));
                if (pathList != null && pathList.size() > 0){
                    ans.add(pathList);
                }
            });
        }
        return ans;
    }

    private String getKeyFromJson(JsonObject jsonObject, List<String> paths) {
        String value = null;
        if (jsonObject != null && paths != null) {
            for (String pathStr : paths) {
                JsonObject findValue = jsonObject;
                String[] pathArr = pathStr.split("\\.");
                for (int i = 0; i < pathArr.length; i++) {
                    if (findValue.has(pathArr[i])) {
                        if (findValue.get(pathArr[i]).isJsonObject()) {
                            findValue = findValue.get(pathArr[i]).getAsJsonObject();
                        } else {
                            if (i == pathArr.length - 1) {
                                value = findValue.get(pathArr[i]).getAsString();
                                return value;
                            } else {
                                break;
                            }
                        }
                    }
                }
            }
        }
        return null;
    }

    public void parseString(String topic ,String content, long receiveTime) {
        JsonObject jsonObject = null;
        if (ifConfig.isLogProject()) {
            jsonObject = gson.fromJson(content, JsonObject.class);
            if (ifConfig.getLogMetadataTopics() != null && ifConfig.getLogMetadataTopics().contains(topic)){
                JsonObject data = processMetadata(jsonObject);
                if (data != null){
                    if (!collectingLogMetadataMap.containsKey(topic)) {
                        collectingLogMetadataMap.put(topic, ConcurrentHashMap.newKeySet());
                    }
                    Set<JsonObject> jsonArray = collectingLogMetadataMap.get(topic);
                    if (jsonArray != null) {
                        jsonArray.add(data);
                    }
                }
            }else {
                JsonObject data = processLogData(jsonObject);
                String projectInfo = getIFProjectAndSystemInfo(jsonObject);
                if (data != null && projectInfo != null) {
                    if (!collectingLogDataMap.containsKey(projectInfo)) {
                        collectingLogDataMap.put(projectInfo, ConcurrentHashMap.newKeySet());
                    }
                    Set<JsonObject> jsonArray = collectingLogDataMap.get(projectInfo);
                    if (jsonArray != null) {
                        jsonArray.add(data);
                    }
                }
            }
        } else {
            if (isJSON) {
                //to do
            } else {
                if (content.startsWith("\"") && content.endsWith("\"")) {
                    content = content.substring(1, content.length() - 1);
                }
                Matcher matcher = dataFormatPattern.matcher(content.trim());
                if (matcher.matches() && namedGroups != null) {
                    List<String> projects = new ArrayList<>();
                    jsonObject = new JsonObject();
                    String projectNameStr = null, instanceName = null, timeStamp = null, metricName = null;
                    double metricValue = 0.0;
                    for (String key : namedGroups.keySet()) {
                        if (key.equalsIgnoreCase(ifConfig.getProjectKey())) {
                            projectNameStr = String.valueOf(matcher.group(key));
                            String[] projectNames = projectNameStr.split(ifConfig.getProjectDelimiter());
                            for (String projectName : projectNames) {
                                if (!projectList.containsKey(projectName)) {
                                    if (ifConfig.isLogParsingInfo()) {
                                        logger.log(Level.INFO, projectName + " not in the projectList ");
                                    }
                                } else {
                                    projects.add(projectName);
                                }
                            }

                        } else if (key.equalsIgnoreCase(ifConfig.getInstanceKey())) {
                            instanceName = String.valueOf(matcher.group(key));
                            if (!instanceList.contains(instanceName)) {
                                if (ifConfig.isLogParsingInfo()) {
                                    logger.log(Level.INFO, instanceName + " not in the instanceList ");
                                }
                                return;
                            }
                        } else if (key.equalsIgnoreCase(ifConfig.getTimestampKey())) {
                            timeStamp = convertToMS(matcher.group(key));
                        } else if (key.equalsIgnoreCase(ifConfig.getMetricKey())) {
                            Matcher metricMatcher = metricPattern.matcher(matcher.group(key));
                            if (metricMatcher.matches()) {
                                metricName = matcher.group(key);
                                metricValue = Double.parseDouble(matcher.group(ifConfig.getValueKey()));
                            } else {
                                if (ifConfig.isLogParsingInfo()) {
                                    logger.log(Level.INFO, "Not match the metric regex " + content);
                                }
                                return;
                            }
                        }
                    }
                    if (projects.size() > 0 && instanceName != null && metricName != null && timeStamp != null) {
                        if (ifConfig.isLogParsingInfo()) {
                            logger.log(Level.INFO, "Parse success " + content);
                        }

                        if (ifConfig.getMetricNameFilter() != null && ifConfig.getMetricNameFilter().equalsIgnoreCase(metricName)) {
                            logger.log(Level.INFO, String.format("%s %s %s", instanceName, metricName, timeStamp));
                        }

                        for (String projectName : projects) {
                            Map<String, String> ifProjectInfo = projectList.get(projectName);
                            String ifProjectName = ifProjectInfo.get("project");
                            String ifSystemName = ifProjectInfo.get("system");
                            if (!collectingDataMap.containsKey(ifProjectName)) {
                                collectingDataMap.put(ifProjectName, new IFStreamingBuffer(ifProjectName, ifSystemName));
                            }
                            collectingDataMap.get(ifProjectName).addData(instanceName, Long.parseLong(timeStamp), metricName, metricValue);
                        }
                    }
                } else {
                    if (ifConfig.isLogParsingInfo()) {
                        logger.log(Level.INFO, " Parse failed, not match the regex " + content);
                    }
                }
            }
        }
    }

    public String convertToMS(String timestamp) {
        StringBuilder stringBuilder = new StringBuilder();
        stringBuilder.append(timestamp);
        if (stringBuilder.length() == 10) {
            stringBuilder.append("000");
        }
        return stringBuilder.toString();
    }

    public void mergeLogDataAndSendToIF2(Map<String, Set<JsonObject>> collectingDataMap) {
        for (String key : collectingDataMap.keySet()) {
            String[] infoArr = key.split("@");
            if (infoArr.length == 2){
                String ifProjectName = infoArr[0];
                String ifSystemName = infoArr[1];
                Lists.partition(Lists.newArrayList(collectingDataMap.get(key)), 1000).forEach(subData->{
                    sendToIF(gson.toJson(subData), ifProjectName, ifSystemName);
                });
                collectingDataMap.remove(key);
            }
        }
        mergeLogMetaDataAndSendToIF2(collectingLogMetadataMap);
    }

    public void mergeLogMetaDataAndSendToIF2(Map<String, Set<JsonObject>> collectingLogMetadataMap){
        if (!collectingLogMetadataMap.isEmpty()){
            for (String key : collectingLogMetadataMap.keySet()) {
                projectList.values().forEach(ifProjectInfo->{
                    String ifProjectName = ifProjectInfo.get("project");
                    String ifSystemName = ifProjectInfo.get("system");
                    sendMetadataToIF(gson.toJson(collectingLogMetadataMap.get(key)), ifProjectName, ifSystemName);
                });
                collectingLogMetadataMap.remove(key);
            }
        }
    }

    public void mergeDataAndSendToIF2(Map<String, IFStreamingBuffer> collectingDataMap) {
        List<IFStreamingBuffer> sendingDataList = new ArrayList<>();
        for (String key : collectedBufferMap.keySet()) {
            if (collectingDataMap.containsKey(key)) {
                IFStreamingBuffer ifStreamingBuffer = collectedBufferMap.get(key).mergeDataAndGetSendingData(collectingDataMap.get(key));
                sendingDataList.add(ifStreamingBuffer);
            } else {
                IFStreamingBuffer ifStreamingBuffer = collectedBufferMap.remove(key);
                sendingDataList.add(ifStreamingBuffer);
            }
        }

        for (String key : collectingDataMap.keySet()) {
            if (!collectedBufferMap.containsKey(key)) {
                collectedBufferMap.put(key, collectingDataMap.remove(key));
            }
        }

        for (IFStreamingBuffer ifSendingBuffer : sendingDataList) {
            convertBackToOldFormat(ifSendingBuffer.getAllInstanceDataMap(), ifSendingBuffer.getProject(), ifSendingBuffer.getSystem(), 10000);
        }
    }

    public void convertBackToOldFormat(Map<String, InstanceData> instanceDataMap, String project, String system, int splitNum) {
        List<String> stringList = new ArrayList<>();
        List<Map<Long, JsonObject>> sortByTimestampMaps = new ArrayList<>();
        Map<Long, JsonObject> sortByTimestampMap = new HashMap<>();
        int total = splitNum;
        for (String instanceName : instanceDataMap.keySet()) {
            InstanceData instanceData = instanceDataMap.get(instanceName);
            Map<Long, DataInTimestamp> dataInTimestampMap = instanceData.getDataInTimestampMap();
            for (Long timestamp : dataInTimestampMap.keySet()) {
                String key = String.format("%s-%s-%d", project, instanceName, timestamp);
                if (filter.mightContain(key)) {
                    if (ifConfig.isLogSendingData()) {
                        if (sendingStatistics.containsKey(key)) {
                            float percent = dataInTimestampMap.get(timestamp).getMetricDataPointSet().size() / sendingStatistics.get(key);
                            long gapSeconds = (System.currentTimeMillis() - sendingTimeStatistics.get(key)) / 1000;
                            String dropStr = String.format("At %s drop data / sent data: %f, time gap: %d seconds", key, percent * 100, gapSeconds);
                            logger.log(Level.INFO, dropStr);
                        } else {
                            String dropStr = String.format("At %s drop data %d", key, dataInTimestampMap.get(timestamp).getMetricDataPointSet().size());
                            logger.log(Level.INFO, dropStr);
                        }
                    }
                    continue;
                }
                filter.put(key);
                if (ifConfig.isLogSendingData()) {
                    sendingStatistics.put(key, dataInTimestampMap.get(timestamp).getMetricDataPointSet().size());
                    sendingTimeStatistics.put(key, System.currentTimeMillis());
                }

                JsonObject thisTimestampObj = sortByTimestampMap.getOrDefault(timestamp, new JsonObject());
                if (!thisTimestampObj.has("timestamp")) {
                    thisTimestampObj.addProperty("timestamp", timestamp.toString());
                }
                Set<MetricDataPoint> metricDataPointSet = dataInTimestampMap.get(timestamp)
                        .getMetricDataPointSet();
                if (total - metricDataPointSet.size() < 0) {
                    total = splitNum;
                    if (!sortByTimestampMap.isEmpty()) {
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
        if (!sortByTimestampMap.isEmpty()) {
            sendToIF(sortByTimestampMap, project, system);
        }
    }

    public void sendToIF(Map<Long, JsonObject> sortByTimestampMap, String project, String system) {
        JsonArray ret = new JsonArray();
        for (JsonObject jsonObject : sortByTimestampMap.values()) {
            ret.add(jsonObject);
        }
        sendToIF(ret.toString(), project, system);
    }

    public void sendMetadataToIF(String data, String ifProjectName, String ifSystemName) {
        String dataType = ifConfig.isLogProject() ? "Log" : "Metric";
        if (projectManager.checkAndCreateProject(ifProjectName, ifSystemName, dataType)) {
            UUID uuid = UUID.randomUUID();
            MultiValueMap<String, String> bodyValues = new LinkedMultiValueMap<>();
            bodyValues.add("licenseKey", ifConfig.getLicenseKey());
            bodyValues.add("projectName", ifProjectName);
            bodyValues.add("userName", ifConfig.getUserName());
            bodyValues.add("data", data);
            bodyValues.add("agentType", ifConfig.getAgentType());
            int dataSize = data.getBytes(StandardCharsets.UTF_8).length / 1024;
            webClient.post()
                    .uri("/api/v1/agent-upload-instancemetadata")
                    .header(HttpHeaders.CONTENT_TYPE, MediaType.APPLICATION_JSON_VALUE)
                    .body(BodyInserters.fromFormData(bodyValues))
                    .retrieve()
                    .bodyToMono(String.class)
                    .timeout(Duration.ofMillis(100000))
                    .onErrorResume(throwable -> {
                        return Mono.just("RETRY");
                    })
                    .subscribe(res -> {
                        if (res.equalsIgnoreCase("RETRY")) {//retry 1 2
                            logger.log(Level.INFO, "sending metadata: request id : " + uuid + " data size: " + dataSize + " kb code: " + res);
                        } else {
                            logger.log(Level.INFO, "sending metadata: request id: " + uuid + " data size: " + dataSize + " kb code: " + res);
                        }
                    });
        }
    }

    public void sendToIF(String data, String ifProjectName, String ifSystemName) {
        String dataType = ifConfig.isLogProject() ? "Log" : "Metric";
        if (projectManager.checkAndCreateProject(ifProjectName, ifSystemName, dataType)) {
            UUID uuid = UUID.randomUUID();
            MultiValueMap<String, String> bodyValues = new LinkedMultiValueMap<>();
            bodyValues.add("licenseKey", ifConfig.getLicenseKey());
            bodyValues.add("projectName", ifProjectName);
            bodyValues.add("userName", ifConfig.getUserName());
            bodyValues.add("metricData", data);
            bodyValues.add("agentType", ifConfig.getAgentType());
            int dataSize = data.getBytes(StandardCharsets.UTF_8).length / 1024;
            webClient.post()
                    .uri("/api/v1/customprojectrawdata")
                    .header(HttpHeaders.CONTENT_TYPE, MediaType.APPLICATION_JSON_VALUE)
                    .body(BodyInserters.fromFormData(bodyValues))
                    .retrieve()
                    .bodyToMono(String.class)
                    .timeout(Duration.ofMillis(100000))
                    .onErrorResume(throwable -> {
                        return Mono.just("RETRY");
                    })
                    .subscribe(res -> {
                        if (res.equalsIgnoreCase("RETRY")) {//retry 1 2
                            logger.log(Level.INFO, "sending data: request id: " + uuid + " data size: " + dataSize + " kb code: " + res);
                        } else {
                            logger.log(Level.INFO, "sending data: request id: " + uuid + " data size: " + dataSize + " kb code: " + res);
                        }
                    });
        }
    }

}
