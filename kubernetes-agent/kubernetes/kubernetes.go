package kubernetes

import (
	"context"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/rest"
	"k8s.io/client-go/tools/clientcmd"
	"k8s.io/client-go/util/homedir"
	"log"
)

type KubernetesServer struct {
	// Construct Variables
	ConnectionType string // remote or in_cluster

	Client *kubernetes.Clientset
}

func (k *KubernetesServer) Initialize() {
	if k.ConnectionType == "in_cluster" {
		// in_cluster
		config, err := rest.InClusterConfig()
		if err != nil {
			panic(err.Error())
		}
		k.Client, err = kubernetes.NewForConfig(config)
		if err != nil {
			panic(err.Error())
		}
	} else {
		// Build connection from the kubeconfig file under home directory
		home := homedir.HomeDir()
		kubeConfig := home + "/.kube/config"
		config, err := clientcmd.BuildConfigFromFlags("", kubeConfig)
		if err != nil {
			panic(err.Error())
		}
		k.Client, err = kubernetes.NewForConfig(config)
		if err != nil {
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

/**
 * Get all pods in the cluster
 */
func (k *KubernetesServer) GetPodsNodesMap() *map[string]string {
	var podsNodesMap = make(map[string]string)
	pods, err := k.Client.CoreV1().Pods("").List(context.Background(), metav1.ListOptions{})
	if err != nil {
		panic(err.Error())
	}
	for _, pod := range pods.Items {
		podsNodesMap[pod.Name] = pod.Spec.NodeName
	}
	return &podsNodesMap
}
