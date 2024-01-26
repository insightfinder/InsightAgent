package com.insightfinder.kubeactions.controller;

import com.fasterxml.jackson.databind.node.ObjectNode;
import com.google.gson.Gson;
import com.google.gson.JsonObject;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AdmissionReviewController {
    @Autowired
    private Gson gson;
    @PostMapping(path = "/mutate")
    public JsonObject processAdmissionReviewRequest(@RequestBody String data) {
        return gson.fromJson(data, JsonObject.class);
    }
}
