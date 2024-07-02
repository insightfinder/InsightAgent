package com.insightfinder.KafkaCollectorAgent.logic;

import static com.insightfinder.KafkaCollectorAgent.logic.utils.Utilities.convertTimestampToMS;

import com.google.common.collect.Lists;
import com.google.common.hash.BloomFilter;
import com.google.common.hash.Funnels;
import com.google.gson.Gson;
import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import com.insightfinder.KafkaCollectorAgent.logic.config.IFConfig;
import com.insightfinder.KafkaCollectorAgent.logic.logstreaming.LogProjectConfigParser;
import com.insightfinder.KafkaCollectorAgent.logic.logstreaming.LogMessageHandler;
import com.insightfinder.KafkaCollectorAgent.logic.metricstreaming.MetricProjectConfigParser;
import com.insightfinder.KafkaCollectorAgent.model.KafkaMessageId;
import com.insightfinder.KafkaCollectorAgent.model.ProjectInfo;
import com.insightfinder.KafkaCollectorAgent.model.ProjectListKey;
import com.insightfinder.KafkaCollectorAgent.model.logmessage.LogMessage;
import com.insightfinder.KafkaCollectorAgent.model.logmetadatamessage.LogMetadataMessage;
import io.micrometer.core.instrument.MeterRegistry;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.nio.charset.Charset;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Map.Entry;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.logging.Level;
import java.util.logging.Logger;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Collectors;
import javax.annotation.PostConstruct;
import lombok.Getter;
import lombok.RequiredArgsConstructor;
import lombok.Setter;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;

@Component
@RequiredArgsConstructor
@Getter
@Setter
public class IFStreamingBufferManager {

  private static final Set<String> metricFilterSet = new HashSet<>();

  static {
    metricFilterSet.add("kafka.consumer.fetch.manager.records.lag");
    metricFilterSet.add("kafka.consumer.fetch.manager.records.lag.max");
    metricFilterSet.add("kafka.consumer.fetch.manager.bytes.consumed.rate");
    metricFilterSet.add("kafka.consumer.fetch.manager.records.consumed.rate");
    metricFilterSet.add("kafka.consumer.fetch.manager.fetch.rate");
  }

  private final ConcurrentHashMap<String, IFStreamingBuffer> collectingDataMap = new ConcurrentHashMap<>();
  private final ConcurrentHashMap<ProjectInfo, Set<JsonObject>> collectingLogDataMap = new ConcurrentHashMap<>();
  private final ConcurrentHashMap<ProjectInfo, Set<JsonObject>> collectingLogMetadataMap = new ConcurrentHashMap<>();
  private final ConcurrentHashMap<String, IFStreamingBuffer> collectedBufferMap = new ConcurrentHashMap<>();
  private final ConcurrentHashMap<String, Integer> sendingStatistics = new ConcurrentHashMap<>();
  private final ConcurrentHashMap<String, Long> sendingTimeStatistics = new ConcurrentHashMap<>();
  BloomFilter<String> filter = BloomFilter.create(
      Funnels.stringFunnel(Charset.defaultCharset()),
      100000000);
  private final Logger logger = Logger.getLogger(IFStreamingBufferManager.class.getName());
  @Autowired
  private final MeterRegistry registry;
  @Autowired
  private final Gson gson;
  @Autowired
  private final IFConfig ifConfig;
  @Autowired
  private final IFProjectManager projectManager;
  @Autowired
  private final WebClient webClient;
  @Autowired
  private final MetricProjectConfigParser metricProjectConfigParser;
  @Autowired
  private final LogProjectConfigParser logProjectConfigParser;
  @Autowired
  private final LogMessageHandler logMessageHandler;
  @Autowired
  private final WebClientEndpoints webClientEndpoints;
  private Map<String, ProjectInfo> metricProjectList; // project name -> info
  private Map<ProjectListKey, ProjectInfo> logProjectList; // datasetId -> info
  private List<ProjectInfo> logMetadataProjectList;
  private boolean isJSON;
  private Pattern dataFormatPattern;
  private Map<String, Integer> namedGroups;
  private Pattern metricPattern;
  private Set<String> instanceList;
  private ExecutorService executorService;

  @SuppressWarnings("unchecked")
  private static Map<String, Integer> getNamedGroups(Pattern regex)
      throws NoSuchMethodException, SecurityException,
      IllegalAccessException, IllegalArgumentException,
      InvocationTargetException {
    Method namedGroupsMethod = Pattern.class.getDeclaredMethod("namedGroups");
    namedGroupsMethod.setAccessible(true);
    Map<String, Integer> namedGroups;
    namedGroups = (Map<String, Integer>) namedGroupsMethod.invoke(regex);
    if (namedGroups == null) {
      throw new InternalError();
    }
    return Collections.unmodifiableMap(namedGroups);
  }

  @PostConstruct
  public void init()
      throws InvocationTargetException, NoSuchMethodException, IllegalAccessException {
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
    instanceList = ifConfig.getInstanceList();
    if (ifConfig.getProjectList() != null) {
      if (ifConfig.isLogProject()) {
        logProjectList = logProjectConfigParser.getLogProjectMapping();
        logMetadataProjectList = logProjectList.entrySet().stream()
            .filter(entry -> !entry.getKey().hasDatasetName())
            .map(Entry::getValue)
            .collect(Collectors.toList());
        logMetadataProjectList.forEach(projectInfo -> collectingLogMetadataMap.put(projectInfo,
            ConcurrentHashMap.newKeySet()));
      } else {
        metricProjectList = metricProjectConfigParser.getMetricProjectMapping();
      }
    }
    //timer thread
    executorService = Executors.newFixedThreadPool(5);
    executorService.execute(() -> {
      int printMetricsTimer = ifConfig.getKafkaMetricLogInterval();
      int sentTimer = ifConfig.getBufferingTime();
      int logMetadataSentTimer = ifConfig.getLogMetadataBufferingTime();
      while (true) {
        if (sentTimer <= 0) {
          sentTimer = ifConfig.getBufferingTime();
          //sending data thread
          executorService.execute(() -> {
            if (ifConfig.isLogProject()) {
              logger.info("sending log data");
              mergeLogDataAndSendToIF(collectingLogDataMap);
            } else {
              logger.info("sending metric data");
              mergeDataAndSendToIF(collectingDataMap);
            }
          });
        }

        if (logMetadataSentTimer <= 0) {
          logMetadataSentTimer = ifConfig.getLogMetadataBufferingTime();
          executorService.execute(() -> {
            if (ifConfig.isLogProject()) {
              logger.info("sending metadata");
              mergeLogMetaDataAndSendToIF(collectingLogMetadataMap);
            }
          });
        }

        if (printMetricsTimer <= 0) {
          printMetricsTimer = ifConfig.getKafkaMetricLogInterval();
          registry.getMeters().forEach(meter -> {
            if (metricFilterSet.contains(meter.getId().getName())) {
              meter.measure().forEach(measurement -> logger.log(Level.INFO,
                  String.format("%s %s : %f", meter.getId().getTag("client.id"),
                      meter.getId().getName(), measurement.getValue())));
            }
          });
        }
        try {
          Thread.sleep(1000);
          printMetricsTimer--;
          sentTimer--;
          logMetadataSentTimer--;
        } catch (InterruptedException e) {
          throw new RuntimeException(e);
        }
      }
    });
  }

  public void parseString(String topic, String content, long receiveTime) {
    if (ifConfig.isLogProject()) {
      if (isLogMetadataMessage(topic)) {
        // handle log metadata message
        logger.info("received metadata: " + content);
        handleLogMetadataMessage(content);
      } else {
        // handle log message
        logger.info("received log: " + content);
        handleLogMessage(content);
      }
    } else {
      if (isJSON) {
        //to do
      } else {
        // handle metric message
        if (content.startsWith("\"") && content.endsWith("\"")) {
          content = content.substring(1, content.length() - 1);
        }
        Matcher matcher = dataFormatPattern.matcher(content.trim());
        if (matcher.matches() && namedGroups != null) {
          List<String> projects = new ArrayList<>();
          String projectNameStr, instanceName = null, timeStamp = null, metricName = null;
          double metricValue = 0.0;
          for (String key : namedGroups.keySet()) {
            if (key.equalsIgnoreCase(ifConfig.getProjectKey())) {
              projectNameStr = String.valueOf(matcher.group(key));
              String[] projectNames = projectNameStr.split(ifConfig.getProjectDelimiter());
              for (String projectName : projectNames) {
                if (!metricProjectList.containsKey(projectName)) {
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
              timeStamp = convertTimestampToMS(matcher.group(key));
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
          if (!projects.isEmpty() && instanceName != null && metricName != null
              && timeStamp != null) {
            if (ifConfig.isLogParsingInfo()) {
              logger.log(Level.INFO, "Parse success " + content);
            }

            if (ifConfig.getMetricNameFilter() != null && ifConfig.getMetricNameFilter()
                .equalsIgnoreCase(metricName)) {
              logger.log(Level.INFO,
                  String.format("%s %s %s", instanceName, metricName, timeStamp));
            }

            for (String projectName : projects) {
              ProjectInfo ifProjectInfo = metricProjectList.get(projectName);
              String ifProjectName = ifProjectInfo.getProject();
              String ifSystemName = ifProjectInfo.getSystem();
              IFStreamingBuffer ifStreamingBuffer = collectedBufferMap.getOrDefault(ifProjectName,
                  new IFStreamingBuffer(ifProjectName, ifSystemName));
              ifStreamingBuffer.addData(instanceName, Long.parseLong(timeStamp), metricName,
                  metricValue);
              collectedBufferMap.put(ifSystemName, ifStreamingBuffer);
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

  private ProjectInfo getIFProjectInfoFromLogMessageId(KafkaMessageId messageId) {
    for (ProjectListKey projectListKey : logProjectList.keySet()) {
      if (projectListKey.matchedMessageId(messageId)) {
        return logProjectList.get(projectListKey);
      }
    }
    return null;
  }

  private boolean isLogMetadataMessage(String topic) {
    return ifConfig.getLogMetadataTopics() != null && ifConfig.getLogMetadataTopics()
        .contains(topic);
  }

  private void handleLogMetadataMessage(String message) {
    LogMetadataMessage logMetadataMessage = logMessageHandler.processMetadataMessage(message);
    if (logMetadataMessage != null && logMetadataMessage.getOutputMessage() != null) {
      collectingLogMetadataMap.values()
          .forEach(jsonObjects -> jsonObjects.add(logMetadataMessage.getOutputMessage()));
    }
  }

  private void handleLogMessage(String message) {
    LogMessage logMessage = logMessageHandler.processLogDataMessage(message);
    if (logMessage != null) {
      ProjectInfo projectInfo = getIFProjectInfoFromLogMessageId(logMessage.getId());
      if (projectInfo != null) {
        Set<JsonObject> jsonArray = collectingLogDataMap.getOrDefault(projectInfo,
            ConcurrentHashMap.newKeySet());
        if (jsonArray != null) {
          jsonArray.add(logMessage.getOutputMessage());
          collectingLogDataMap.put(projectInfo, jsonArray);
        }
      }
    }
  }

  public void mergeLogDataAndSendToIF(Map<ProjectInfo, Set<JsonObject>> collectingLogDataMap) {
    for (ProjectInfo projectInfo : collectingLogDataMap.keySet()) {
      if (projectInfo.getProject() != null && projectInfo.getSystem() != null) {
        String ifProjectName = projectInfo.getProject();
        String ifSystemName = projectInfo.getSystem();
        Lists.partition(Lists.newArrayList(collectingLogDataMap.get(projectInfo)), 1000)
            .forEach(subData -> webClientEndpoints.sendLogDataToIF(gson.toJson(subData), ifProjectName,
                ifSystemName));
        collectingLogDataMap.remove(projectInfo);
      }
    }
  }

  public void mergeLogMetaDataAndSendToIF(
      Map<ProjectInfo, Set<JsonObject>> collectingLogMetadataMap) {
    for (ProjectInfo projectInfo : collectingLogMetadataMap.keySet()) {
      if (projectInfo.getProject() != null && projectInfo.getSystem() != null) {
        String ifProjectName = projectInfo.getProject();
        String ifSystemName = projectInfo.getSystem();
        if (!collectingLogMetadataMap.get(projectInfo).isEmpty()) {
          webClientEndpoints.sendMetadataToIF(
              gson.toJson(collectingLogMetadataMap.get(projectInfo)), ifProjectName,
              ifSystemName);
        }
      }
      collectingLogMetadataMap.put(projectInfo, ConcurrentHashMap.newKeySet());
    }
  }

  public void mergeDataAndSendToIF(Map<String, IFStreamingBuffer> collectingDataMap) {
    List<IFStreamingBuffer> sendingDataList = new ArrayList<>();
    for (String key : collectedBufferMap.keySet()) {
      if (collectingDataMap.containsKey(key)) {
        IFStreamingBuffer ifStreamingBuffer = collectedBufferMap.get(key)
            .mergeDataAndGetSendingData(collectingDataMap.get(key));
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
      convertBackToOldFormat(ifSendingBuffer.getAllInstanceDataMap(), ifSendingBuffer.getProject(),
          ifSendingBuffer.getSystem(), 10000);
    }
  }

  public void convertBackToOldFormat(Map<String, InstanceData> instanceDataMap, String project,
      String system, int splitNum) {
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
              float percent = dataInTimestampMap.get(timestamp).getMetricDataPointSet().size()
                  / sendingStatistics.get(key);
              long gapSeconds =
                  (System.currentTimeMillis() - sendingTimeStatistics.get(key)) / 1000;
              String dropStr = String.format(
                  "At %s drop data / sent data: %f, time gap: %d seconds", key, percent * 100,
                  gapSeconds);
              logger.log(Level.INFO, dropStr);
            } else {
              String dropStr = String.format("At %s drop data %d", key,
                  dataInTimestampMap.get(timestamp).getMetricDataPointSet().size());
              logger.log(Level.INFO, dropStr);
            }
          }
          continue;
        }
        filter.put(key);
        if (ifConfig.isLogSendingData()) {
          sendingStatistics.put(key,
              dataInTimestampMap.get(timestamp).getMetricDataPointSet().size());
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
    webClientEndpoints.sendLogDataToIF(ret.toString(), project, system);
  }
}
