package com.insightfinder.KafkaCollectorAgent.logic.metricstreaming.parser;

import static com.insightfinder.KafkaCollectorAgent.logic.utils.Utilities.convertTimestampToMS;

import com.insightfinder.KafkaCollectorAgent.logic.config.IFConfig;
import com.insightfinder.KafkaCollectorAgent.logic.metricstreaming.MetricProjectConfigParser;
import com.insightfinder.KafkaCollectorAgent.model.ProjectInfo;
import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.logging.Level;
import java.util.logging.Logger;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import lombok.RequiredArgsConstructor;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

/**
 * Lenovo metric parsing. Non-JSON messages are parsed with the configured {@code dataFormatRegex}
 * named groups (project / instance / timestamp / metric / value); the project is looked up against
 * the configured {@code projectList} and the instance is filtered by {@code instanceList}.
 *
 * <p>JSON metric parsing is not implemented for Lenovo yet (it was a no-op on master).
 *
 * <p>Selected when {@code insight-finder.vendor} is {@code lenovo} or unset (the historical
 * default).
 */
@Component
@RequiredArgsConstructor
@ConditionalOnProperty(name = "insight-finder.vendor", havingValue = "lenovo", matchIfMissing = true)
public class LenovoMetricMessageParser implements MetricMessageParser {

  private final Logger logger = Logger.getLogger(LenovoMetricMessageParser.class.getName());
  private final IFConfig ifConfig;
  private final MetricProjectConfigParser metricProjectConfigParser;

  private Map<String, ProjectInfo> metricProjectList; // project name -> info
  private boolean isJSON;
  private Pattern dataFormatPattern;
  private Map<String, Integer> namedGroups;
  private Pattern metricPattern;
  private Set<String> instanceList;

  @SuppressWarnings("unchecked")
  private static Map<String, Integer> getNamedGroups(Pattern regex) {
    try {
      Method namedGroupsMethod = Pattern.class.getDeclaredMethod("namedGroups");
      namedGroupsMethod.setAccessible(true);
      Map<String, Integer> namedGroups = (Map<String, Integer>) namedGroupsMethod.invoke(regex);
      if (namedGroups == null) {
        throw new InternalError();
      }
      return Collections.unmodifiableMap(namedGroups);
    } catch (ReflectiveOperationException e) {
      throw new IllegalStateException("Unable to read named groups from regex", e);
    }
  }

  @Override
  public void init() {
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
      metricProjectList = metricProjectConfigParser.getMetricProjectMapping();
    }
  }

  @Override
  public List<MetricRecord> parse(String content) {
    if (isJSON) {
      // TODO: Lenovo JSON metric parsing not implemented (no-op on master).
      return Collections.emptyList();
    }
    return parseRegex(content);
  }

  private List<MetricRecord> parseRegex(String content) {
    if (content.startsWith("\"") && content.endsWith("\"")) {
      content = content.substring(1, content.length() - 1);
    }
    Matcher matcher = dataFormatPattern.matcher(content.trim());
    if (!matcher.matches() || namedGroups == null) {
      if (ifConfig.isLogParsingInfo()) {
        logger.log(Level.INFO, " Parse failed, not match the regex " + content);
      }
      return Collections.emptyList();
    }
    List<String> projects = new ArrayList<>();
    String projectNameStr;
    String instanceName = null;
    String timeStamp = null;
    String metricName = null;
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
          return Collections.emptyList();
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
          return Collections.emptyList();
        }
      }
    }
    List<MetricRecord> records = new ArrayList<>();
    if (!projects.isEmpty() && instanceName != null && metricName != null && timeStamp != null) {
      if (ifConfig.isLogParsingInfo()) {
        logger.log(Level.INFO, "Parse success " + content);
      }
      if (ifConfig.getMetricNameFilter() != null
          && ifConfig.getMetricNameFilter().equalsIgnoreCase(metricName)) {
        logger.log(Level.INFO, String.format("%s %s %s", instanceName, metricName, timeStamp));
      }
      for (String projectName : projects) {
        records.add(MetricRecord.builder()
            .projectInfo(metricProjectList.get(projectName))
            .instanceName(instanceName)
            .timestamp(Long.parseLong(timeStamp))
            .metricName(metricName)
            .value(metricValue)
            .build());
      }
    }
    return records;
  }
}
