package com.insightfinder.KafkaCollectorAgent.logic;

import javax.annotation.Nullable;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;

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
     * Generate valid column name e.g. CPU[ip-172-31-60-25]:-633995270
     *
     * @return
     */
    public String generateHeader(boolean includeGroup) {
        if (includeGroup) {
            return getMetric() + LEFT_PARENTHESIS + getInstance() +
                    RIGHT_PARENTHESIS + COLON + getGroup();
        }
        return getMetric() + LEFT_PARENTHESIS + getInstance() +
                RIGHT_PARENTHESIS;
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
