package com.insightfinder.KafkaCollectorAgent;

import javax.annotation.Nullable;
import java.util.*;

public class MetricHeaderEntity {
    String metric;
    String instance;
    String group;

    public MetricHeaderEntity(String metric, String instance, String group) {
        this.metric = metric;
        this.instance = instance;
        this.group = group;
    }

    @Nullable
    public static synchronized MetricHeaderEntity parse(String fullMetricName) {
        if (fullMetricName.equalsIgnoreCase("timestamp")) {
            return null;
        } else {
            String[] metricNameAndGroupId = getMetricNameAndGroupId(fullMetricName);
            String firstPart = metricNameAndGroupId[0];
            int idx1 = firstPart.indexOf(91);
            if (idx1 < 1) {
                return null;
            } else {
                int idx2 = firstPart.indexOf(93, idx1);
                if (idx2 >= 2 && idx1 < idx2) {
                    String instanceName = metricNameAndGroupId[0].substring(idx1 + 1, idx2);
                    String metricName = metricNameAndGroupId[0].substring(0, idx1);
                    int generatedID = (instanceName + metricName).hashCode();
                    String groupId = String.valueOf(generatedID);
                    return new MetricHeaderEntity(metricName, instanceName, groupId);
                } else {
                    return null;
                }
            }
        }
    }

    public String generateHeader(boolean includeGroup) {
        return includeGroup ? this.getMetric() + "[" + this.getInstance() + "]" + ":" + this.getGroup() : this.getMetric() + "[" + this.getInstance() + "]";
    }

    private static String[] getMetricNameAndGroupId(String s) {
        String[] arrays = new String[2];
        int lastColIndex = s.lastIndexOf(":");
        int lastICIndex = s.lastIndexOf(93);
        if (s.contains(":") && s.lastIndexOf(":") != s.length() && lastColIndex > lastICIndex) {
            String[] temp = new String[]{s.substring(0, s.lastIndexOf(":")), s.substring(s.lastIndexOf(":") + 1)};
            if (temp.length == 2) {
                return temp;
            }

            StringBuilder metricNameBuilder = new StringBuilder();

            for(int i = 0; i < temp.length - 1; ++i) {
                metricNameBuilder.append(temp[i]);
            }

            arrays[0] = metricNameBuilder.toString();
            arrays[1] = temp[temp.length - 1];
        } else {
            arrays[0] = s;
        }

        return arrays;
    }

    public static Set<String> parseKeySetForTraining(List<String> columns) {
        Set<String> result = null;
        if (columns != null) {
            result = new HashSet();
            Iterator var2 = columns.iterator();

            while(var2.hasNext()) {
                String colName = (String)var2.next();
                MetricHeaderEntity entity = parse(colName);
                if (entity != null) {
                    result.add(entity.instance + entity.metric);
                }
            }
        }

        return result;
    }

    public static Set<String> getMetricNameSet(List<String> columns, String componentName) {
        Set<String> result = null;
        if (columns != null) {
            result = new HashSet();
            Iterator var3 = columns.iterator();

            while(var3.hasNext()) {
                String colName = (String)var3.next();
                MetricHeaderEntity entity = parse(colName);
                if (entity != null) {
                    result.add(componentName + entity.metric);
                }
            }
        }

        return result;
    }

    public String generateHeaderString() {
        return this.metric + "[" + this.instance + "]:" + this.group;
    }

    public String getMetric() {
        return this.metric;
    }

    public void setMetric(String metric) {
        this.metric = metric;
    }

    public String getInstance() {
        return this.instance;
    }

    public void setInstance(String instance) {
        this.instance = instance;
    }

    public String getGroup() {
        return this.group;
    }

    public void setGroup(String group) {
        this.group = group;
    }

    public boolean equals(Object o) {
        if (this == o) {
            return true;
        } else if (o != null && this.getClass() == o.getClass()) {
            MetricHeaderEntity that = (MetricHeaderEntity)o;
            return Objects.equals(this.metric, that.metric) && Objects.equals(this.instance, that.instance);
        } else {
            return false;
        }
    }

    public int hashCode() {
        return Objects.hash(new Object[]{this.metric, this.instance});
    }
}
