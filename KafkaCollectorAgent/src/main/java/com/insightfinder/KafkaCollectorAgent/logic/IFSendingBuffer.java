package com.insightfinder.KafkaCollectorAgent.logic;

import com.google.gson.JsonObject;
import java.util.ArrayList;
import java.util.List;

public class IFSendingBuffer {
    private String project;
    private List<JsonObject> jsonObjectList;
    private int size;

    public IFSendingBuffer(IFStreamingBuffer ifStreamingBuffer) {
        jsonObjectList = new ArrayList<>();
        project = ifStreamingBuffer.getProject();
        size = 0;
        jsonObjectList.add(ifStreamingBuffer.getData());
    }

    public void addData(IFStreamingBuffer ifStreamingBuffer){
        if (ifStreamingBuffer != null){
            jsonObjectList.add(ifStreamingBuffer.getData());
        }
    }

    public String getProject() {
        return project;
    }

    public void setProject(String project) {
        this.project = project;
    }

    public List<JsonObject> getJsonObjectList() {
        return jsonObjectList;
    }

    public void setJsonObjectList(List<JsonObject> jsonObjectList) {
        this.jsonObjectList = jsonObjectList;
    }
}
