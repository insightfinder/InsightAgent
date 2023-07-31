package kubernetes

import (
	"context"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/rest"
	"k8s.io/client-go/tools/clientcmd"
	"k8s.io/client-go/util/homedir"
	"log"
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
			log.Output(2, "Created Kubernetes config (from 'kubeconfig' file).")
		} else {
			k.Client = nil
		}
	} else {
		k.Client = nil
	}

	// Build connection from the in-cluster config
	if k.Client == nil {
		log.Output(2, "Try to connect to Kubernetes cluster (in-cluster).")
		config, err := rest.InClusterConfig()
		if err == nil {
			k.Client, err = kubernetes.NewForConfig(config)
			if err == nil {
				log.Output(2, "Created Kubernetes config (from in-cluster).")
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
		log.Output(2, "Failed to connect to Kubernetes cluster.")
		panic(err.Error())
	} else {
		log.Output(2, "Successfully connected to Kubernetes cluster.")
	}
}

func (k *KubernetesServer) GetTargetReplicas(namespace string) map[string]map[string]int32 {
	targetReplicas := make(map[string]map[string]int32)

	deployments, _ := k.Client.AppsV1().Deployments(namespace).List(context.Background(), metav1.ListOptions{})
	statefulSets, _ := k.Client.AppsV1().StatefulSets(namespace).List(context.Background(), metav1.ListOptions{})

	// Process replicaSets
	for _, deployment := range deployments.Items {
		if _, ok := targetReplicas["Deployment"]; !ok {
			targetReplicas["Deployment"] = make(map[string]int32)
		}
		targetReplicas["Deployment"][deployment.Name] = deployment.Status.Replicas
	}

	// Process statefulSets
	for _, statefulSet := range statefulSets.Items {
		if _, ok := targetReplicas["StatefulSet"]; !ok {
			targetReplicas["StatefulSet"] = make(map[string]int32)
		}
		targetReplicas["StatefulSet"][statefulSet.Name] = statefulSet.Status.Replicas

	}

	return targetReplicas

}

//func (k *KubernetesServer) GetPodsChangesInEvents(namespace string) (map[string]map[string]map[string]bool, map[string]map[string]map[string]bool) {
//	creationEvents := make(map[string]map[string]map[string]bool)
//	deletionEvents := make(map[string]map[string]map[string]bool)
//	replicaSetEventList, _ := k.Client.CoreV1().Events(namespace).List(context.Background(), metav1.ListOptions{FieldSelector: "involvedObject.kind=ReplicaSet"})
//	statefulSetEventList, _ := k.Client.CoreV1().Events(namespace).List(context.Background(), metav1.ListOptions{FieldSelector: "involvedObject.kind=StatefulSet"})
//
//	// Combine all events
//	allEvents := make([]corev1.Event, 0)
//	allEvents = append(allEvents, replicaSetEventList.Items...)
//	allEvents = append(allEvents, statefulSetEventList.Items...)
//
//	// Process replicaSetEvents
//	for _, event := range allEvents {
//
//		// Convert ReplicaSet to its parent Deployment
//		resourceKind := event.InvolvedObject.Kind
//		resourceName := event.InvolvedObject.Name
//		if event.InvolvedObject.Kind == "ReplicaSet" {
//			replicaSet, _ := k.Client.AppsV1().ReplicaSets(namespace).Get(context.Background(), event.InvolvedObject.Name, metav1.GetOptions{})
//			if replicaSet.OwnerReferences != nil && replicaSet.OwnerReferences[0].Kind == "Deployment" {
//				resourceKind = "Deployment"
//				resourceName = replicaSet.OwnerReferences[0].Name
//			} else {
//				// Skip this non-Deployment ReplicaSet
//				continue
//			}
//		}
//
//		if _, ok := creationEvents[resourceKind]; !ok {
//			creationEvents[resourceKind] = make(map[string]map[string]bool)
//			deletionEvents[resourceKind] = make(map[string]map[string]bool)
//		}
//
//		if event.Reason == "SuccessfulDelete" {
//			if _, ok := deletionEvents[resourceKind][resourceName]; !ok {
//				deletionEvents[resourceKind][resourceName] = make(map[string]bool)
//			}
//			deletionEvents[resourceKind][resourceName][getPodNameFromEventMessage(event.Message)] = true
//		} else if event.Reason == "SuccessfulCreate" {
//			if _, ok := creationEvents[resourceKind][resourceName]; !ok {
//				creationEvents[resourceKind][resourceName] = make(map[string]bool)
//			}
//			creationEvents[resourceKind][resourceName][getPodNameFromEventMessage(event.Message)] = true
//		}
//	}
//
//	// Create changeEvents by removing duplicates
//	for resourceKind, resourceEvents := range deletionEvents {
//		for resourceName, deletedPods := range resourceEvents {
//			for deletedPod, _ := range deletedPods {
//				if findPodInEvents(deletedPod, resourceKind, resourceName, &creationEvents) {
//					delete(creationEvents[resourceKind][resourceName], deletedPod)
//				}
//			}
//		}
//	}
//
//	return creationEvents, deletionEvents
//
//}

func (k *KubernetesServer) GetPods(namespace string) map[string]map[string]map[string]bool {
	result := make(map[string]map[string]map[string]bool)
	allPods, _ := k.Client.CoreV1().Pods(namespace).List(context.Background(), metav1.ListOptions{})
	for _, pod := range allPods.Items {

		// Only work with running pods
		if pod.Status.Phase != corev1.PodRunning {
			continue
		}

		// Determine the parent resourceKind of this pod
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
	return result
}
