package com.insightfinder.kubeactions.controller;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import io.kubernetes.client.custom.Quantity;
import io.kubernetes.client.custom.V1Patch;
import io.kubernetes.client.openapi.ApiClient;
import io.kubernetes.client.openapi.ApiException;
import io.kubernetes.client.openapi.Configuration;
import io.kubernetes.client.openapi.apis.AppsV1Api;
import io.kubernetes.client.openapi.apis.CoreV1Api;
import io.kubernetes.client.openapi.models.*;
import io.kubernetes.client.util.ClientBuilder;
import io.kubernetes.client.util.Config;
import io.kubernetes.client.util.PatchUtils;
import org.jose4j.json.internal.json_simple.JSONObject;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;
import javax.annotation.PostConstruct;
import java.io.IOException;
import java.math.BigDecimal;
import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import java.util.stream.Collectors;

@Component
public class K8SManager {
    private static final Logger log = LoggerFactory.getLogger(K8SManager.class);
    @Value("${spring.profiles.active}")
    private String activeProfile;
    private CoreV1Api coreV1Api = null;
    private AppsV1Api appsV1Api = null;
    @PostConstruct
    void init() {
        ApiClient client = null;
        try {
            if (activeProfile != null && activeProfile.equalsIgnoreCase("k8s")){
                client = ClientBuilder
                        .cluster()
                        .build();
            }else {
                client = Config.defaultClient();
            }

        } catch (IOException e) {
            log.atError().log(e.getStackTrace().toString());
        }
        Configuration.setDefaultApiClient(client);
        coreV1Api = new CoreV1Api();
        appsV1Api = new AppsV1Api();
    }


    public List<String> getAllNameSpaces() throws ApiException {
        try {
            V1NamespaceList listNamespace =
                    coreV1Api.listNamespace(
                            null, null, null, null, null, null, null, null, null, null);
            List<String> list =
                    listNamespace.getItems().stream()
                            .map(v1Namespace -> v1Namespace.getMetadata().getName())
                            .collect(Collectors.toList());
            return list;
        }catch (ApiException exception){
            log.atError().log(exception.getStackTrace().toString());
        }
        return null;
    }

    public List<String> getPods(){
        V1PodList v1podList =
                null;
        try {
            v1podList = coreV1Api.listPodForAllNamespaces(
                    null, null, null, null, null, null, null, null, null, null);
        } catch (ApiException e) {
            log.atError().log(e.getStackTrace().toString());
        }
        List<String> podList =
                v1podList.getItems().stream()
                        .map(v1Pod -> v1Pod.getMetadata().getName())
                        .collect(Collectors.toList());
        return podList;
    }

    public Map<String, List<String>> getNodes(String namespace) {
        Map<String, List<String>> nodeMap = new HashMap<>();
        V1PodList v1podList = null;
        try {
            v1podList = coreV1Api.listNamespacedPod(namespace, null, null, null, null, null, null, null, null, null, null);
        } catch (ApiException e) {
            log.atError().log(e.getStackTrace().toString());
        }
        v1podList.getItems().stream().forEach(v1Pod -> {
            if (!nodeMap.containsKey(v1Pod.getSpec().getNodeName())){
                nodeMap.put(v1Pod.getSpec().getNodeName(), new ArrayList<>());
            }
            nodeMap.get(v1Pod.getSpec().getNodeName()).add(v1Pod.getMetadata().getName());
        });
        return nodeMap;
    }

    public Map<String, List<String>> getNodes(){
        Map<String, List<String>> nodeMap = new HashMap<>();
        V1PodList v1podList = null;
        try {
            v1podList = coreV1Api.listPodForAllNamespaces(null, null, null, null, null, null, null, null, null, null);
        } catch (ApiException e) {
            log.atError().log(e.getStackTrace().toString());
        }
        v1podList.getItems().stream().forEach(v1Pod -> {
            if (!nodeMap.containsKey(v1Pod.getSpec().getNodeName())){
                nodeMap.put(v1Pod.getSpec().getNodeName(), new ArrayList<>());
            }
            nodeMap.get(v1Pod.getSpec().getNodeName()).add(v1Pod.getMetadata().getName());
        });
        return nodeMap;
    }

    public void deletePod(String nodeName, String namespace,String podName){
        Map<String, List<String>> nodes = getNodes();
        if (nodes.containsKey(nodeName)){
            Set<String> pods = new HashSet<>(nodes.get(nodeName));
            if (pods.contains(podName)){
                V1Pod v1Pod = null;
                try {
                    v1Pod = coreV1Api.deleteNamespacedPod(podName, namespace, null, null, null, null, null, null);
                } catch (ApiException e) {
                    log.atError().log(e.getStackTrace().toString());
                }
                if (v1Pod != null){
                    log.atInfo().log("Deleted pod " + v1Pod.getMetadata().getName());
                }else {
                    log.atInfo().log("Pod not found " + podName);
                }
            }
        }else {
            log.atInfo().log("Node not found " + nodeName);
        }
    }

    public void deletePod(String nodeName,String podName){
        Map<String, List<String>> nodes = getNodes();
        if (nodes.containsKey(nodeName)){
            Set<String> pods = new HashSet<>(nodes.get(nodeName));
            if (pods.contains(podName)){
                V1Pod v1Pod = null;
                try {
                    v1Pod = coreV1Api.deleteNamespacedPod(podName, "default", null, null, null, null, null, null);
                } catch (ApiException e) {
                    log.atError().log(e.getStackTrace().toString());
                }
                if (v1Pod != null){
                    log.atInfo().log("Deleted pod " + v1Pod.getMetadata().getName());
                }else {
                    log.atInfo().log("Pod not found " + podName);
                }
            }
        }else {
            log.atInfo().log("Node not found " + nodeName);
        }
    }

    public List<V1Node> listNodes(){
        V1NodeList v1NodeList = null;
        try {
            v1NodeList = coreV1Api.listNode(null, null, null, null, null, null, null, null, null, null);
        } catch (ApiException e) {
            log.atError().log(e.getStackTrace().toString());
        }
        return v1NodeList.getItems();
    }

    public boolean scaleBy(String nameSpace, String deploymentName, int podNum) {
        V1Deployment v1Deployment = null;
        try {
            v1Deployment = getDeployment(nameSpace, deploymentName);
        } catch (ApiException e) {
            log.atError().log(e.getStackTrace().toString());
        }
        int finalNum = v1Deployment.getSpec().getReplicas() + podNum;
        String jsonPatchStrTemplate =
                "[{\"op\":\"replace\",\"path\":\"/spec/replicas\",\"value\":%d}]";
        String jsonPatchStr = String.format(jsonPatchStrTemplate, finalNum);
        return execPatch(v1Deployment, jsonPatchStr);
    }

    public boolean scaleTo(String nameSpace, String deploymentName, int podNum){
        V1Deployment v1Deployment = null;
        try {
            v1Deployment = getDeployment(nameSpace, deploymentName);
        } catch (ApiException e) {
            log.atError().log(e.getStackTrace().toString());
        }
        String jsonPatchStrTemplate =
                "[{\"op\":\"replace\",\"path\":\"/spec/replicas\",\"value\":%d}]";
        String jsonPatchStr = String.format(jsonPatchStrTemplate, podNum);
        return execPatch(v1Deployment, jsonPatchStr);
    }

    public boolean verticalScaleTo(String nameSpace, String deploymentName, float cpu, float mem)  {
        V1Deployment v1Deployment = null;
        try {
            v1Deployment = getDeployment(nameSpace, deploymentName);
        } catch (ApiException e) {
            log.atError().log(e.getStackTrace().toString());
        }
        JsonArray jsonArray = new JsonArray();
        v1Deployment.getSpec().getTemplate().getSpec().getContainers().forEach(v1Container -> {
            JsonObject jsonObject = new JsonObject();
            jsonArray.add(jsonObject);
        });
        return execPatch(v1Deployment, jsonArray);
    }

    public long getContainerMemLimit(String nameSpace, String deploymentName, String container) {
        V1Deployment v1Deployment = null;
        try {
            v1Deployment = getDeployment(nameSpace, deploymentName);
        } catch (ApiException e) {
            log.atError().log(e.getStackTrace().toString());
        }
        AtomicLong retValue = new AtomicLong();
        v1Deployment.getSpec().getTemplate().getSpec().getContainers().forEach(v1Container -> {
            if (v1Container.getName().equalsIgnoreCase(container)){
                Quantity quantity = v1Container.getResources().getLimits().get("memory");
                if (quantity != null){
                    BigDecimal ret = quantity.getNumber().divide(new BigDecimal(1024 * 1024));
                    retValue.set(ret.longValue());
                }
            }
        });
        return retValue.get();
    }

    public long getContainerMemRequest(String nameSpace, String deploymentName, String container) {
        V1Deployment v1Deployment = null;
        try {
            v1Deployment = getDeployment(nameSpace, deploymentName);
        } catch (ApiException e) {
            log.atError().log(e.getStackTrace().toString());
        }
        AtomicLong retValue = new AtomicLong();
        v1Deployment.getSpec().getTemplate().getSpec().getContainers().forEach(v1Container -> {
            if (v1Container.getName().equalsIgnoreCase(container)){
                Quantity quantity = v1Container.getResources().getRequests().get("memory");
                if (quantity != null){
                    BigDecimal ret = quantity.getNumber().divide(new BigDecimal(1024 * 1024));
                    retValue.set(ret.longValue());
                }
            }
        });
        return retValue.get();
    }

    public JSONObject getContainerMem(String nameSpace, String deploymentName, String container) {
        V1Deployment v1Deployment = null;
        try {
            v1Deployment = getDeployment(nameSpace, deploymentName);
        } catch (ApiException e) {
            log.atError().log(e.getStackTrace().toString());
        }
        JSONObject retValue = new JSONObject();
        v1Deployment.getSpec().getTemplate().getSpec().getContainers().forEach(v1Container -> {
            if (v1Container.getName().equalsIgnoreCase(container)){
                Quantity quantity = v1Container.getResources().getRequests().get("memory");
                if (quantity != null){
                    BigDecimal ret = quantity.getNumber().divide(new BigDecimal(1024 * 1024));
                    retValue.put("requestMem", ret.longValue());
                }
                Quantity quantity2 = v1Container.getResources().getLimits().get("memory");
                if (quantity2 != null){
                    BigDecimal ret = quantity2.getNumber().divide(new BigDecimal(1024 * 1024));
                    retValue.put("limitMem", ret.longValue());
                }
            }
        });
        return retValue;
    }

    public boolean setContainerMem(String nameSpace, String deploymentName, String container, long limitMem, long requestMem) {
        V1Deployment v1Deployment = null;
        try {
            v1Deployment = getDeployment(nameSpace, deploymentName);
        } catch (ApiException e) {
            log.atError().log(e.getStackTrace().toString());
        }
        JsonArray jsonArray = new JsonArray();
        AtomicInteger index = new AtomicInteger();
        v1Deployment.getSpec().getTemplate().getSpec().getContainers().forEach(v1Container -> {
            if (v1Container.getName().equalsIgnoreCase(container)){
                Quantity quantity = v1Container.getResources().getRequests().get("memory");
                if (quantity != null){
                    JsonObject jsonObject = new JsonObject();
                    jsonObject.addProperty("op", "replace");
                    jsonObject.addProperty("path", String.format("/spec/template/spec/containers/%d/resources/requests/memory", index.get()));
                    jsonObject.addProperty("value", requestMem+"m");
                    jsonArray.add(jsonObject);
                }
                Quantity quantity2 = v1Container.getResources().getLimits().get("memory");
                if (quantity2 != null){
                    JsonObject jsonObject = new JsonObject();
                    jsonObject.addProperty("op", "replace");
                    jsonObject.addProperty("path", String.format("/spec/template/spec/containers/%d/resources/limits/memory", index.get()));
                    jsonObject.addProperty("value", limitMem+"m");
                    jsonArray.add(jsonObject);
                }
            }
            index.set(index.get() + 1);
        });
        if (!jsonArray.isEmpty()){
           return execPatch(v1Deployment, jsonArray);
        }
        return false;
    }


    public void verticalScaleBy(String nameSpace, String deploymentName, float cpu, float mem) {
        V1Deployment v1Deployment = null;
        try {
            v1Deployment = getDeployment(nameSpace, deploymentName);
        } catch (ApiException e) {
            log.atError().log(e.getStackTrace().toString());
        }
        V1Deployment finalV1Deployment = v1Deployment;
        v1Deployment.getSpec().getTemplate().getSpec().getContainers().forEach(v1Container -> {
//            v1Container.getResources().getLimits();
//            v1Container.getResources().getRequests();
            String jsonPatchStrTemplate =
                    "[{\"op\":\"replace\",\"path\":\"/spec/template/spec/containers/0/resources/requests/cpu\",\"value\":%.1f}]";
            String jsonPatchStr = String.format(jsonPatchStrTemplate, cpu);
            try {
                V1Deployment deploy =
                        PatchUtils.patch(
                                V1Deployment.class,
                                () ->
                                        appsV1Api.patchNamespacedDeploymentCall(
                                                finalV1Deployment.getMetadata().getName(),
                                                nameSpace,
                                                new V1Patch(jsonPatchStr),
                                                null,
                                                null,
                                                null,
                                                null, // field-manager is optional
                                                null,null),
                                V1Patch.PATCH_FORMAT_JSON_PATCH,
                                appsV1Api.getApiClient());
            } catch (ApiException e) {
                throw new RuntimeException(e);
            }
        });
    }

    private boolean execPatch(V1Deployment v1Deployment, String jsonPatchStr){
        try {
            V1Deployment deploy =
                    PatchUtils.patch(
                            V1Deployment.class,
                            () ->
                                    appsV1Api.patchNamespacedDeploymentCall(
                                            v1Deployment.getMetadata().getName(),
                                            v1Deployment.getMetadata().getNamespace(),
                                            new V1Patch(jsonPatchStr),
                                            null,
                                            null,
                                            null,
                                            null, // field-manager is optional
                                            null,null),
                            V1Patch.PATCH_FORMAT_JSON_PATCH,
                            appsV1Api.getApiClient());
        } catch (ApiException e) {
            return false;
        }
        return true;
    }

    private boolean execPatch(V1Deployment v1Deployment, JsonArray jsonPatchArr){
        return execPatch(v1Deployment, jsonPatchArr.toString());
    }

    private V1Deployment getDeployment(String nameSpace, String deploymentName) throws ApiException {
        V1Deployment  v1Deployment = null;
        try {
            v1Deployment = appsV1Api.readNamespacedDeployment(deploymentName, nameSpace, null);
        } catch (ApiException e) {
            throw e;
        }
        return v1Deployment;
    }

}