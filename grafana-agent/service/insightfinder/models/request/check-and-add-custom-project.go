package request

type CheckAndAddCustomProjectRequest struct {
	Operation        string `json:"operation,omitempty" url:"operation,omitempty"`
	UserName         string `json:"userName,omitempty" url:"userName,omitempty"`
	LicenseKey       string `json:"licenseKey,omitempty" url:"licenseKey,omitempty"`
	ProjectName      string `json:"projectName,omitempty" url:"projectName,omitempty"`
	SystemName       string `json:"systemName,omitempty" url:"systemName,omitempty"`
	InstanceType     string `json:"instanceType,omitempty" url:"instanceType,omitempty"`
	ProjectCloudType string `json:"projectCloudType,omitempty" url:"projectCloudType,omitempty"`
	DataType         string `json:"dataType,omitempty" url:"dataType,omitempty"`
	InsightAgentType string `json:"insightAgentType,omitempty" url:"insightAgentType,omitempty"`
	SamplingInterval int    `json:"samplingInterval,omitempty" url:"samplingInterval,omitempty"`
}
