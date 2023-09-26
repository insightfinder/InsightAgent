package tools

import (
	"encoding/json"
	"fmt"
	"kubernetes-agent/kubernetes"
	"log"
	"os"
	"strconv"
	"strings"
)

type InstanceMapper struct {
	KubernetesServer kubernetes.KubernetesServer

	// Storage[Namespace][Deployment / StatefulSets][deployment-1]{0: pod-1, 1: pod-2, 2: pod-3}
	Storage map[string]map[string]map[string]map[string]string
}

func (mapper *InstanceMapper) AddNamespace(namespaceFilter string) {

	for _, namespace := range strings.Split(namespaceFilter, ",") {
		namespace = strings.ReplaceAll(namespace, " ", "")
		if mapper.Storage[namespace] == nil {
			mapper.Storage[namespace] = make(map[string]map[string]map[string]string)
		}
	}
}

func (mapper *InstanceMapper) Initialize() {

	// Initialize Kubernetes Server
	kubernetesServer := kubernetes.KubernetesServer{}
	kubernetesServer.Initialize()
	mapper.KubernetesServer = kubernetesServer

	// Initialize Storage
	if mapper.Load() {
		fmt.Println("Read configs from InstanceMapper.json")
	} else {
		fmt.Println("Starting a scratch instance mapper")
	}

	// Create Storage
	if mapper.Storage == nil {
		mapper.Storage = make(map[string]map[string]map[string]map[string]string)
	}
}

func (mapper *InstanceMapper) UpdateSlots(namespace string, resourceKind string, resourceReplicas map[string]int32) {
	// Create resourceKind record IfNotExist
	if mapper.Storage[namespace][resourceKind] == nil {
		mapper.Storage[namespace][resourceKind] = make(map[string]map[string]string)
	}

	for resource, replicas := range resourceReplicas {
		// Create resource record IfNotExist
		if mapper.Storage[namespace][resourceKind][resource] == nil {
			mapper.Storage[namespace][resourceKind][resource] = make(map[string]string)
		}
		slots := mapper.Storage[namespace][resourceKind][resource]

		// Create slots if not exist
		if slots == nil {
			slots = make(map[string]string)
		}

		// Skip slots if it is already enough
		if int32(len(slots)) >= replicas {
			continue
		} else {
			// Create missing slots
			for slot := 0; slot < int(replicas); slot++ {
				slotStr := strconv.Itoa(slot)
				if _, ok := slots[slotStr]; !ok {
					slots[slotStr] = ""
				}
			}
		}

	}
}

func (mapper *InstanceMapper) DeletePods(namespace string, resourceKind string, resources map[string]map[string]bool) {
	for resource, pods := range resources {
		for pod, _ := range pods {
			slots := mapper.Storage[namespace][resourceKind][resource]
			if slots != nil {
				for index, podSlot := range slots {
					if podSlot == pod {
						delete(slots, index)
					}
				}
				mapper.Storage[namespace][resourceKind][resource] = slots
			}
		}
	}
}

func (mapper *InstanceMapper) AddPods(namespace string, resourceKind string, resources map[string]map[string]bool) {
	if resourceKind == "DaemonSet" {
		return
	}
	for resource, pods := range resources {
		slots := mapper.Storage[namespace][resourceKind][resource]
		if slots != nil {
			for pod, _ := range pods {
				if mapper.FindIndexByPodName(namespace, resourceKind, resource, pod) == "-1" {
					for slot, podInSlot := range slots {
						if podInSlot == "" {
							slots[slot] = pod
							break
						}
					}
				}
			}
		}
		mapper.Storage[namespace][resourceKind][resource] = slots
	}
}

func (mapper *InstanceMapper) Update() {
	log.Output(2, "Start updating Pod Instance Mapping...")

	for namespace, _ := range mapper.Storage {
		podsCreated, podsDeleted := mapper.GetDiffMap(namespace)
		targetReplicas := mapper.KubernetesServer.GetTargetReplicas(namespace)

		// Delete pods in slots
		for resourceKind, resources := range podsDeleted {
			// Create resourceKind record IfNotExist
			if mapper.Storage[namespace][resourceKind] == nil {
				mapper.Storage[namespace][resourceKind] = make(map[string]map[string]string)
			}

			// Remove deleted pods from slots
			mapper.DeletePods(namespace, resourceKind, resources)
		}

		// Scale Slots based on targetReplicas
		for resourceKind, resources := range targetReplicas {
			mapper.UpdateSlots(namespace, resourceKind, resources)
		}

		// Add newlyCreatedPods to slots
		for resourceKind, resources := range podsCreated {
			mapper.AddPods(namespace, resourceKind, resources)
		}
	}
	mapper.Save()
	log.Output(2, "Pod Instance Mapping updated successfully!")
}

func (mapper *InstanceMapper) FindIndexByPodName(namespace string, resourceKind string, resource string, podName string) string {
	for index, pod := range mapper.Storage[namespace][resourceKind][resource] {
		if pod == podName {
			return index
		}
	}
	return "-1"
}

func (mapper *InstanceMapper) GetInstanceMapping(namespace string, podName string) (string, string) {
	for resourceKind, resources := range mapper.Storage[namespace] {
		for resource, _ := range resources {
			mappingIndex := mapper.FindIndexByPodName(namespace, resourceKind, resource, podName)
			if mappingIndex != "-1" {
				return resource + "-" + mappingIndex, resource
			}
		}
	}
	return "", ""
}

// Load Data from disk
func (mapper *InstanceMapper) Load() bool {
	b, e := os.ReadFile("storage/InstanceMapper.json")
	if e != nil {
		return false
	}
	e = json.Unmarshal(b, &mapper.Storage)
	if e != nil {
		return false
	}
	return true
}

// Save the database to the disk
func (mapper *InstanceMapper) Save() {
	b, e := json.Marshal(mapper.Storage)
	if e != nil {
		panic(e)
	}
	os.WriteFile("storage/InstanceMapper.json", b, 0644)

}

// GetDiffMap returns the createdPods and deletedPods
func (mapper *InstanceMapper) GetDiffMap(namespace string) (map[string]map[string]map[string]bool, map[string]map[string]map[string]bool) {
	// Initial the diff maps
	deletePods := make(map[string]map[string]map[string]bool)
	createPods := make(map[string]map[string]map[string]bool)
	K8sCurrentPods := mapper.KubernetesServer.GetPods(namespace)

	// Get the deleted pods by comparing the current pods and the storage
	for resourceKind, resources := range mapper.Storage[namespace] {
		for resource, pods := range resources {
			for _, pod := range pods {
				if _, ok := K8sCurrentPods[resourceKind][resource][pod]; !ok {
					if deletePods[resourceKind] == nil {
						deletePods[resourceKind] = make(map[string]map[string]bool)
					}
					if deletePods[resourceKind][resource] == nil {
						deletePods[resourceKind][resource] = make(map[string]bool)
					}
					deletePods[resourceKind][resource][pod] = true
				}
			}
		}
	}

	// Get the created pods by comparing the current pods and the storage
	for resourceKind, resources := range K8sCurrentPods {
		for resource, pods := range resources {
			for pod, _ := range pods {
				if mapper.FindIndexByPodName(namespace, resourceKind, resource, pod) == "-1" {
					if createPods[resourceKind] == nil {
						createPods[resourceKind] = make(map[string]map[string]bool)
					}
					if createPods[resourceKind][resource] == nil {
						createPods[resourceKind][resource] = make(map[string]bool)
					}
					createPods[resourceKind][resource][pod] = true
				}
			}
		}
	}

	return createPods, deletePods
}

func (mapper *InstanceMapper) ListPods(namespace string) []string {
	var allPods []string
	for _, resources := range mapper.Storage[namespace] {
		for _, pods := range resources {
			for _, pod := range pods {
				allPods = append(allPods, pod)
			}
		}
	}
	return allPods
}
