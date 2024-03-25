package insightfinder

type ProjectCheckModel struct {
	Success        bool `json:"success"`
	IsProjectExist bool `json:"isProjectExist"`
}

type ProjectCreationModel struct {
	Operation                 string `json:"operation"`
	UserName                  string `json:"userName"`
	LicenseKey                string `json:"licenseKey"`
	ProjectName               string `json:"projectName"`
	SystemName                string `json:"systemName"`
	InstanceType              string `json:"instanceType"`
	ProjectCloudType          string `json:"projectCloudType"`
	DataType                  string `json:"dataType"`
	InsightAgentType          string `json:"insightAgentType"`
	SamplingInterval          int    `json:"samplingInterval"`
	SamplingIntervalInSeconds int    `json:"samplingIntervalInSeconds"`
}
