package com.insightfinder.kubeactions.controller;

import io.kubernetes.client.openapi.ApiException;
import io.kubernetes.client.openapi.models.V1Deployment;
import io.kubernetes.client.openapi.models.V1Node;
import org.jose4j.json.internal.json_simple.JSONObject;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/k8s")
public class K8SController {
    @Autowired
    private K8SManager k8SManager;

    @GetMapping("/namespaces")
    public List<String> allNamespace(@RequestHeader(required = true) String serverId) throws ApiException {
        return k8SManager.getAllNameSpaces();
    }

    @GetMapping("/pods")
    public List<String> allPods(@RequestHeader(required = true) String serverId) throws ApiException {
        return k8SManager.getPods();
    }

    @GetMapping("/nodes")
    public Map<String, List<String>> nodeToPods(@RequestHeader(required = true) String serverId) throws ApiException {
        return k8SManager.getNodes();
    }

    @GetMapping("/nodesinfo")
    public List<V1Node> nodesinfo(@RequestHeader(required = true) String serverId) throws ApiException {
        return k8SManager.listNodes();
    }

    @GetMapping("/nodes/{namespace}")
    public Map<String, List<String>> nodeToPods(@RequestHeader(required = true) String serverId, @PathVariable String namespace) throws ApiException {
        return k8SManager.getNodes(namespace);
    }

    @DeleteMapping("/del/{namespace}/{nodeName}/{podName}")
    public ResponseEntity<String> deletePod(@RequestHeader(required = true) String serverId, @PathVariable String namespace, @PathVariable String nodeName, @PathVariable String podName) throws ApiException {
        k8SManager.deletePod(nodeName, namespace, podName);
        return new ResponseEntity<>(HttpStatus.OK);
    }

    @PostMapping("/scale/{namespace}/{deployment}/{num}")
    public ResponseEntity<String> scaleBy(@RequestHeader(required = true) String serverId, @PathVariable String namespace, @PathVariable String deployment, @PathVariable int num) throws ApiException {
        k8SManager.scaleBy(namespace, deployment, num);
        return new ResponseEntity<>(HttpStatus.OK);
    }

    @PostMapping("/scale/{namespace}/{deployment}/{cpu}/{mem}")
    public ResponseEntity<String> verticalScaleBy(@RequestHeader(required = true) String serverId, @PathVariable String namespace, @PathVariable String deployment, @PathVariable float cpu, @PathVariable float mem) throws ApiException {
        k8SManager.verticalScaleBy(namespace, deployment, cpu, mem);
        return new ResponseEntity<>(HttpStatus.OK);
    }

    @GetMapping("/limit/{namespace}/{deployment}/{container}")
    public long getContainerMemLimit(@RequestHeader(required = true) String serverId, @PathVariable String namespace, @PathVariable String deployment, @PathVariable String container) throws ApiException {
        return k8SManager.getContainerMemLimit(namespace, deployment, container);
    }

    @GetMapping("/res/{namespace}/{deployment}")
    public JSONObject getContainerMemRequest(@RequestHeader(required = true) String serverId, @PathVariable String namespace, @PathVariable String deployment) throws ApiException {
        StringBuilder stringBuilder = new StringBuilder();
        V1Deployment v1Deployment = k8SManager.getV1Deployment(namespace, deployment, stringBuilder);
        JSONObject retValue = new JSONObject();
        if (v1Deployment != null){
            retValue.put("deployment", v1Deployment.toString());
        }else{
            retValue.put("errors", stringBuilder.toString());
        }
        return retValue;
    }

    @GetMapping("/res/{namespace}/{deployment}/{container}")
    public JSONObject getContainerMem(@RequestHeader(required = true) String serverId, @PathVariable String namespace, @PathVariable String deployment, @PathVariable String container) throws ApiException {
        return k8SManager.getContainerMem(namespace, deployment, container);
    }

//    @GetMapping("/res/{namespace}/{podName}/{container}")
//    public JSONObject getContainerMemByPodName(@RequestHeader(required = true) String serverId, @PathVariable String namespace, @PathVariable String podName, @PathVariable String container) throws ApiException {
//        return k8SManager.getContainerMemByPodName(namespace, podName, container);
//    }

    @PostMapping("/res/{namespace}/{deployment}/{container}/limitMem/requestMem")
    public ResponseEntity<String> setContainerMem(@RequestHeader(required = true) String serverId, @PathVariable String namespace, @PathVariable String deployment, @PathVariable String container, long limitMem, long requestMem) throws ApiException {
        StringBuilder stringBuilder = new StringBuilder();
        if (k8SManager.setContainerMem(namespace, deployment, container, limitMem, requestMem, stringBuilder)){
            return new ResponseEntity<>(HttpStatus.OK);
        }else {
            return new ResponseEntity<>(stringBuilder.toString(), HttpStatus.FORBIDDEN);
        }
    }
}
