package kubernetes

import (
	"context"
	"fmt"
	"k8s.io/apimachinery/pkg/fields"
	"k8s.io/client-go/tools/cache"
	"log"
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

func (k *KubernetesServer) GetTargetReplicas(namespace string) *map[string]map[string]int32 {
	targetReplicas := make(map[string]map[string]int32)

	deployments, _ := k.Client.AppsV1().Deployments(namespace).List(context.Background(), metav1.ListOptions{})
	statefulSets, _ := k.Client.AppsV1().StatefulSets(namespace).List(context.Background(), metav1.ListOptions{})

	// Process replicaSets
	for _, deployment := range deployments.Items {
		if _, ok := targetReplicas["Deployment"]; !ok {
			targetReplicas["Deployment"] = make(map[string]int32)
		}
		targetReplicas["Deployment"][deployment.Name] = *deployment.Spec.Replicas
	}

	// Process statefulSets
	for _, statefulSet := range statefulSets.Items {
		if _, ok := targetReplicas["StatefulSet"]; !ok {
			targetReplicas["StatefulSet"] = make(map[string]int32)
		}
		targetReplicas["StatefulSet"][statefulSet.Name] = *statefulSet.Spec.Replicas

	}

	return &targetReplicas

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

func (k *KubernetesServer) GetPVCPodsMapping(namespace string) *map[string]string {
	var result map[string]string = make(map[string]string)
	Pods, _ := k.Client.CoreV1().Pods(namespace).List(context.TODO(), metav1.ListOptions{})
	for _, pod := range Pods.Items {
		for _, volume := range pod.Spec.Volumes {
			if volume.PersistentVolumeClaim != nil {
				PVC := volume.PersistentVolumeClaim.ClaimName
				result[PVC] = pod.Name
			}
		}
	}
	return &result
}

func testFun(oldObj, newObj interface{}) {

	newPod := newObj.(*corev1.Pod)
	for _, containerStatus := range newPod.Status.ContainerStatuses {
		if containerStatus.State.Terminated != nil {
			fmt.Printf("Pod Name: %s - Container Name: %s\n", newPod.Name, containerStatus.Name)
			fmt.Printf("Exit Code: %d\n", containerStatus.State.Terminated.ExitCode)
			fmt.Printf("Reason: %s\n", containerStatus.State.Terminated.Reason)
			fmt.Printf("Message: %s\n", containerStatus.State.Terminated.Message)
		}
	}

}

func (k *KubernetesServer) WatchContainerStatus(namespace string) {
	listWatch := cache.NewListWatchFromClient(
		k.Client.CoreV1().RESTClient(),
		"pods",
		namespace,
		fields.Everything(),
	)
	_, controller := cache.NewInformer(
		listWatch,
		&corev1.Pod{},
		0,
		cache.ResourceEventHandlerFuncs{
			UpdateFunc: testFun,
		},
	)
	stop := make(chan struct{})
	defer close(stop)
	controller.Run(stop)
}
