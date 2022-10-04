package com.insightfinder.KafkaCollectorAgent.logic;

import com.google.gson.JsonObject;

import java.util.Objects;
import java.util.logging.Logger;

public class IFStreamingBuffer {
    private Logger logger = Logger.getLogger(IFStreamingBuffer.class.getName());
    private String project;
    private String timestamp;
    private String instanceName;
    private JsonObject data;

    public IFStreamingBuffer() {
        data = new JsonObject();
    }
    public IFStreamingBuffer(IFStreamingBuffer ifStreamingBuffer) {
        this.project = ifStreamingBuffer.getProject();
        this.timestamp = ifStreamingBuffer.getTimestamp();
        this.instanceName = ifStreamingBuffer.getInstanceName();
        this.data = new JsonObject();
        this.data.addProperty("timestamp", this.timestamp);
    }

    public IFStreamingBuffer(String projectName, String instanceName, String timestamp, JsonObject jsonObject) {
        this.project = projectName;
        this.timestamp = timestamp;
        this.instanceName = instanceName;
        this.data = new JsonObject();
        this.data.addProperty("timestamp", this.timestamp);
        parseAndUpdate(jsonObject);
    }

    public void parseAndUpdate(JsonObject jsonObject){
        for (String key : jsonObject.keySet()){
            data.addProperty(key+"["+instanceName+"]", jsonObject.get(key).getAsString().trim());
        }
    }

    public IFStreamingBuffer merge(IFStreamingBuffer ifStreamingBuffer){
        if (this.project.equalsIgnoreCase(ifStreamingBuffer.project)
                && this.instanceName.equalsIgnoreCase(ifStreamingBuffer.instanceName)
                && this.timestamp.equalsIgnoreCase(ifStreamingBuffer.timestamp)){
            for (String key : ifStreamingBuffer.data.keySet()){
                this.data.addProperty(key, ifStreamingBuffer.data.get(key).getAsString().trim());
            }
        }
        return this;
    }

    public Logger getLogger() {
        return logger;
    }

    public void setLogger(Logger logger) {
        this.logger = logger;
    }

    public String getProject() {
        return project;
    }

    public void setProject(String project) {
        this.project = project;
    }

    public String getTimestamp() {
        return timestamp;
    }

    public void setTimestamp(String timestamp) {
        this.timestamp = timestamp;
    }

    public String getInstanceName() {
        return instanceName;
    }

    public void setInstanceName(String instanceName) {
        this.instanceName = instanceName;
    }

    public JsonObject getData() {
        return data;
    }

    public void setData(JsonObject data) {
        this.data = data;
    }

    @Override
    public boolean equals(Object o) {
        if (this == o) return true;
        if (o == null || getClass() != o.getClass()) return false;
        IFStreamingBuffer that = (IFStreamingBuffer) o;
        return Objects.equals(logger, that.logger) && Objects.equals(project, that.project) && Objects.equals(timestamp, that.timestamp) && Objects.equals(instanceName, that.instanceName) && Objects.equals(data, that.data);
    }

    @Override
    public int hashCode() {
        return Objects.hash(logger, project, timestamp, instanceName, data);
    }
}
