package kubernetes

import "time"

type EventEntity struct {
	Name      string          `json:"name"`
	Namespace string          `json:"namespace"`
	Time      time.Time       `json:"time"`
	Type      string          `json:"type"`
	Note      string          `json:"note"`
	Reason    string          `json:"reason"`
	Regarding RegardingEntity `json:"regarding"`
}

type RegardingEntity struct {
	Name      string `json:"name"`
	Namespace string `json:"namespace"`
	Kind      string `json:"kind"`
	Container string `json:"container,omitempty"`
}

type PVCMountPoint struct {
	PVC       string `json:"pvc"`
	Container string `json:"container"`
	MountName string `json:"mountName"`
	MountPath string `json:"mountPath"`
}
