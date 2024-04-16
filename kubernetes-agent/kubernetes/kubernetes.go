package kubernetes

import (
	"context"
	"fmt"
	"log/slog"
	"regexp"
	"time"

	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/rest"
	"k8s.io/client-go/tools/clientcmd"
	"k8s.io/client-go/util/homedir"
)

type KubernetesServer struct {
	Client *kubernetes.Clientset
}

func (k *KubernetesServer) Initialize() {

	// Build connection from the kubeconfig file under home directory
	home := homedir.HomeDir()
	kubeConfig := home + "/.kube/config"
	config, err := clientcmd.BuildConfigFromFlags("", kubeConfig)
	if err == nil {
		k.Client, err = kubernetes.NewForConfig(config)
		if err == nil {
			slog.Info("Created Kubernetes config (from 'kubeconfig' file).")
		} else {
			k.Client = nil
		}
	} else {
		k.Client = nil
	}

	// Build connection from the in-cluster config
	if k.Client == nil {
		slog.Info("Try to connect to Kubernetes cluster (in-cluster).")
		config, err := rest.InClusterConfig()
		if err == nil {
			k.Client, err = kubernetes.NewForConfig(config)
			if err == nil {
				slog.Info("Created Kubernetes config (from in-cluster).")
			} else {
				k.Client = nil
				panic(err.Error())
			}
		} else {
			k.Client = nil
			panic(err.Error())
		}
	}
	k.VerifyConnection()
}

func (k *KubernetesServer) VerifyConnection() {
	_, err := k.Client.CoreV1().Namespaces().List(context.Background(), metav1.ListOptions{})
	if err != nil {
		slog.Info("Failed to connect to Kubernetes cluster.")
		panic(err.Error())
	} else {
		slog.Info("Successfully connected to Kubernetes cluster.")
	}
}

func (k *KubernetesServer) GetCurrentReplicas(namespace string) *map[string]map[string]int32 {
	currentReplicas := make(map[string]map[string]int32)

	deployments, _ := k.Client.AppsV1().Deployments(namespace).List(context.Background(), metav1.ListOptions{})
	statefulSets, _ := k.Client.AppsV1().StatefulSets(namespace).List(context.Background(), metav1.ListOptions{})

	// Process replicaSets
	for _, deployment := range deployments.Items {
		if _, ok := currentReplicas["Deployment"]; !ok {
			currentReplicas["Deployment"] = make(map[string]int32)
		}
		currentReplicas["Deployment"][deployment.Name] = deployment.Status.Replicas
	}

	// Process statefulSets
	for _, statefulSet := range statefulSets.Items {
		if _, ok := currentReplicas["StatefulSet"]; !ok {
			currentReplicas["StatefulSet"] = make(map[string]int32)
		}
		currentReplicas["StatefulSet"][statefulSet.Name] = statefulSet.Status.Replicas

	}

	return &currentReplicas
}
func (k *KubernetesServer) GetEvents(namespace string, startTime time.Time, endTime time.Time) *[]EventEntity {
	results := make([]EventEntity, 0)
	events, err := k.Client.EventsV1().Events(namespace).List(context.Background(), metav1.ListOptions{})
	if err != nil {
		fmt.Println(err)
	}
	for _, event := range events.Items {

		if event.CreationTimestamp.Time.Before(startTime) || event.CreationTimestamp.Time.After(endTime) {
			continue
		}

		result := EventEntity{
			Name:      event.Name,
			Namespace: event.Namespace,
			Time:      event.CreationTimestamp.Time,
			Type:      event.Type,
			Note:      event.Note,
			Reason:    event.Reason,
			Regarding: RegardingEntity{
				Name:      event.Regarding.Name,
				Namespace: event.Regarding.Namespace,
				Kind:      event.Regarding.Kind,
			},
		}

		// Extract Container from Pod events
		if event.Regarding.Kind == "Pod" {
			containerRegex := regexp.MustCompile(`(?i)containers\{(.*?)\}`)
			containerNameMatched := containerRegex.FindStringSubmatch(event.Regarding.FieldPath)
			if containerNameMatched != nil {
				containerName := containerNameMatched[1]
				result.Regarding.Container = containerName
			}
		}

		// Add to the result list
		results = append(results, result)

	}
	return &results
}

func (k *KubernetesServer) GetPods(namespace string) *map[string]map[string]map[string]bool {
	result := make(map[string]map[string]map[string]bool)
	allPods, _ := k.Client.CoreV1().Pods(namespace).List(context.Background(), metav1.ListOptions{})
	for _, pod := range allPods.Items {

		// Only work with running pods
		if pod.Status.Phase != corev1.PodRunning {
			continue
		}

		// Determine the parent resourceKind of this pod
		if pod.OwnerReferences == nil || len(pod.OwnerReferences) == 0 {
			continue
		}
		resourceKind := pod.OwnerReferences[0].Kind
		resourceName := pod.OwnerReferences[0].Name
		if pod.OwnerReferences[0].Kind == "ReplicaSet" {
			// Use the parent resourceKind and resourceName if this replicaSet is owned by a parent resource
			replicaSet, _ := k.Client.AppsV1().ReplicaSets(namespace).Get(context.Background(), pod.OwnerReferences[0].Name, metav1.GetOptions{})
			if replicaSet.OwnerReferences != nil && len(replicaSet.OwnerReferences) > 0 && replicaSet.OwnerReferences[0].Kind != "" && replicaSet.OwnerReferences[0].Name != "" {
				resourceKind = replicaSet.OwnerReferences[0].Kind
				resourceName = replicaSet.OwnerReferences[0].Name
			}
		}

		// Add the resourceKind to the result
		if _, ok := result[resourceKind]; !ok {
			result[resourceKind] = make(map[string]map[string]bool)
		}

		// Add the resourceName to the result
		if _, ok := result[resourceKind][resourceName]; !ok {
			result[resourceKind][resourceName] = make(map[string]bool)
		}

		// Add the pod to the result
		result[resourceKind][resourceName][pod.Name] = true
	}
	return &result
}

func (k *KubernetesServer) GetPodsContainerExitEvents(namespace string, startTime time.Time, endTime time.Time) *[]EventEntity {
	results := make([]EventEntity, 0)
	cache := make(map[string]EventEntity)

	// Get All Pods
	Pods, err := k.Client.CoreV1().Pods(namespace).List(context.TODO(), metav1.ListOptions{})
	if err != nil {
		slog.Error("Failed to get pods in namespace: " + err.Error())
	}
	for _, Pod := range Pods.Items {
		for _, containerStatus := range Pod.Status.ContainerStatuses {
			if containerStatus.LastTerminationState.Terminated != nil {
				containerLastTerminated := containerStatus.LastTerminationState.Terminated
				if containerLastTerminated.FinishedAt.Time.After(startTime) && containerLastTerminated.FinishedAt.Time.Before(endTime) {
					// Save the same event to cache to avoid duplicate events
					cache[fmt.Sprint(Pod.Name, containerStatus.Name, containerLastTerminated.FinishedAt.Time.UnixMilli(), containerLastTerminated.Reason)] = EventEntity{
						Name:      Pod.Name,
						Namespace: Pod.Namespace,
						Time:      containerLastTerminated.FinishedAt.Time,
						Type:      "Warning",
						Reason:    containerLastTerminated.Reason,
						Note:      fmt.Sprintf("Container %s Terminated with exit code %d.", containerStatus.Name, containerLastTerminated.ExitCode),
						Regarding: RegardingEntity{
							Name:      Pod.Name,
							Namespace: Pod.Namespace,
							Kind:      "Pod",
							Container: containerStatus.Name,
						},
					}
				}
			}
		}
	}

	// Add all events to result list.
	for _, event := range cache {
		results = append(results, event)
	}

	return &results
}

func (k *KubernetesServer) GetHostsNameList() []string {
	var hosts []string
	nodes, _ := k.Client.CoreV1().Nodes().List(context.Background(), metav1.ListOptions{})
	for _, node := range nodes.Items {
		hosts = append(hosts, node.Name)
	}
	return hosts
}

func (k *KubernetesServer) GetPodsPVCMapping(namespace string) *map[string]map[string]map[string][]string {
	// PVC -> Pod -> MountName -> [Containers]
	var result = make(map[string]map[string]map[string][]string)

	Pods, _ := k.Client.CoreV1().Pods(namespace).List(context.TODO(), metav1.ListOptions{})
	ContainerVolumeMountMap := k.GetVolumeMountInfoFromPods(Pods)
	for _, pod := range Pods.Items {
		for _, volume := range pod.Spec.Volumes {
			if volume.PersistentVolumeClaim != nil {
				if _, ok := result[pod.Name]; !ok {
					result[pod.Name] = make(map[string]map[string][]string)
				}

				PVC := volume.PersistentVolumeClaim.ClaimName
				mountPointName := volume.Name
				for _, container := range (*ContainerVolumeMountMap)[pod.Name][mountPointName] {
					if _, ok := result[pod.Name][PVC]; !ok {
						result[pod.Name][PVC] = make(map[string][]string)
					}
					result[pod.Name][PVC][mountPointName] = append(result[pod.Name][PVC][mountPointName], container)
				}
			}
		}
	}

	return &result
}

func (k *KubernetesServer) GetVolumeMountInfoFromPods(Pods *corev1.PodList) *map[string]map[string][]string {
	var PodContainerMountMap = make(map[string]map[string]map[string]string)

	// Build PodContainerMountMap: PodName -> ContainerName -> VolumeName -> MountPath
	for _, pod := range Pods.Items {
		if _, ok := PodContainerMountMap[pod.Name]; !ok {
			PodContainerMountMap[pod.Name] = make(map[string]map[string]string)
		}
		for _, container := range pod.Spec.Containers {
			if _, ok := PodContainerMountMap[pod.Name][container.Name]; !ok {
				PodContainerMountMap[pod.Name][container.Name] = make(map[string]string)
			}
			for _, volumeMount := range container.VolumeMounts {
				PodContainerMountMap[pod.Name][container.Name][volumeMount.Name] = volumeMount.MountPath
			}
		}
	}

	// Convert to MountPointMap: Pod -> MountPointName -> list[ContainerNames]
	var MountPointMap = make(map[string]map[string][]string)
	for podName, containerMountMap := range PodContainerMountMap {
		for containerName, volumeMountMap := range containerMountMap {
			for volumeName := range volumeMountMap {
				if _, ok := MountPointMap[podName]; !ok {
					MountPointMap[podName] = make(map[string][]string)
				}
				MountPointMap[podName][volumeName] = append(MountPointMap[podName][volumeName], containerName)
			}
		}
	}
	return &MountPointMap
}

func (k *KubernetesServer) GetOpenTelemetryMapping(namespace string) *map[string]string {
	results := make(map[string]string)

	// Get app.kubernetes.io/component label from all deployments
	Deployments, err := k.Client.AppsV1().Deployments(namespace).List(context.Background(), metav1.ListOptions{LabelSelector: "app.kubernetes.io/component"})
	if err != nil {
		slog.Error("Failed to get deployments in namespace: " + err.Error())
	}

	// Get app.kubernetes.io/component label from all statefulSets
	StatefulSets, err := k.Client.AppsV1().StatefulSets(namespace).List(context.Background(), metav1.ListOptions{LabelSelector: "app.kubernetes.io/component"})
	if err != nil {
		slog.Error("Failed to get statefulSets in namespace: " + err.Error())
	}

	for _, deployment := range Deployments.Items {
		results[deployment.Labels["app.kubernetes.io/component"]] = deployment.Name
	}

	for _, statefulSet := range StatefulSets.Items {
		results[statefulSet.Labels["app.kubernetes.io/component"]] = statefulSet.Name
	}
	return &results
}
