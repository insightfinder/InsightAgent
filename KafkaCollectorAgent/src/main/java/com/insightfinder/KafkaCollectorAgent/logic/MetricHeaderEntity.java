package com.insightfinder.KafkaCollectorAgent.logic;

import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import javax.annotation.Nullable;
public class MetricHeaderEntity {
    public static final String LEFT_PARENTHESIS = "[";
    public static final String RIGHT_PARENTHESIS = "]";
    public static final String LEFT_BRACKET = "(";
    public static final String RIGHT_BRACKET = ")";
    public static final String COLON = ":";
    String metric;
    String instance;
    String group;
    public MetricHeaderEntity(String metric, String instance, String group) {
        this.metric = metric;
        this.instance = instance;
        this.group = group;
    }
    /**
     * Get the metric name object, include the full metric name, instance name and groupid
     *
     * @param fullMetricName
     * @return
     */
    @Nullable
    public static synchronized MetricHeaderEntity parse(String fullMetricName) {
        if (fullMetricName.equalsIgnoreCase("timestamp")) {
            return null;
        }
        String[] metricNameAndGroupId = getMetricNameAndGroupId(fullMetricName);
        String firstPart = metricNameAndGroupId[0];
        int idx1 = firstPart.indexOf('[');
        if (idx1 < 1) {
            return null;
        }
        int idx2 = firstPart.indexOf(']', idx1);
        if (idx2 < 2 || idx1 >= idx2) {
            return null;
        }
        String instanceName = metricNameAndGroupId[0].substring(idx1 + 1, idx2);
        String metricName = metricNameAndGroupId[0].substring(0, idx1);
        int generatedID = (instanceName + metricName).hashCode();
        String groupId = String.valueOf(generatedID);
        return new MetricHeaderEntity(metricName, instanceName, groupId);
    }
    /**
     * Get the metric name object, include the full metric name, instance name and groupid
     *
     * @param fullMetricName
     * @return
     */
    /**
     * Generate valid column name e.g. CPU[ip-172-31-60-25]:-633995270
     *
     * @return
     */
    public String generateHeader(boolean includeGroup) {
        if (includeGroup) {
            return getMetric() +LEFT_PARENTHESIS + getInstance() +
                    RIGHT_PARENTHESIS + COLON + getGroup();
        }
        return getMetric() + LEFT_PARENTHESIS + getInstance() +
                RIGHT_PARENTHESIS;
    }
    /**
     * For some metric it will contains ":" which will break original
     *
     * @param s
     * @return
     */
    private static String[] getMetricNameAndGroupId(String s) {
        String[] arrays = new String[2];
        int lastColIndex = s.lastIndexOf(COLON);
        int lastICIndex = s.lastIndexOf(']');
        if (s.contains(COLON) && s.lastIndexOf(COLON) != s.length()
                && lastColIndex > lastICIndex) {
            String[] temp = {s.substring(0, s.lastIndexOf(COLON)),
                    s.substring(s.lastIndexOf(COLON) + 1)};
            if (temp.length == 2) {
                return temp;
            } else {
                StringBuilder metricNameBuilder = new StringBuilder();
                for (int i = 0; i < temp.length - 1; i++) {
                    metricNameBuilder.append(temp[i]);
                }
                arrays[0] = metricNameBuilder.toString();
                arrays[1] = temp[temp.length - 1];
            }
        } else {
            arrays[0] = s;
        }
        return arrays;
    }
    public static Set<String> parseKeySetForTraining(List<String> columns) {
        Set<String> result = null;
        if (columns != null) {
            result = new HashSet<>();
            for (String colName : columns) {
                MetricHeaderEntity entity = parse(colName);
                if (entity != null) {
                    result.add(entity.instance + entity.metric);
                }
            }
        }
        return result;
    }
    /**
     * Get Log metric name set, using the component name instead of instance name
     *
     * @param columns
     * @param componentName
     * @return
     */
    public static Set<String> getMetricNameSet(List<String> columns, String componentName) {
        Set<String> result = null;
        if (columns != null) {
            result = new HashSet<>();
            for (String colName : columns) {
                MetricHeaderEntity entity = parse(colName);
                if (entity != null) {
                    result.add(componentName + entity.metric);
                }
            }
        }
        return result;
    }
    public String generateHeaderString() {
        return metric + "[" + instance + "]:" + group;
    }
    public String getMetric() {
        return metric;
    }
    public void setMetric(String metric) {
        this.metric = metric;
    }
    public String getInstance() {
        return instance;
    }
    public void setInstance(String instance) {
        this.instance = instance;
    }
    public String getGroup() {
        return group;
    }
    public void setGroup(String group) {
        this.group = group;
    }
    @Override
    public boolean equals(Object o) {
        if (this == o) {
            return true;
        }
        if (o == null || getClass() != o.getClass()) {
            return false;
        }
        MetricHeaderEntity that = (MetricHeaderEntity) o;
        return Objects.equals(metric, that.metric) &&
                Objects.equals(instance, that.instance);
    }
    @Override
    public int hashCode() {
        return Objects.hash(metric, instance);
    }
}
