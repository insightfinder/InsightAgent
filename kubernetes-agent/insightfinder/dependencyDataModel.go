package insightfinder

type DependencyRelationPayload struct {
	SystemDisplayName             string `json:"systemDisplayName" validate:"required"`
	LicenseKey                    string `json:"licenseKey" validate:"required"`
	UserName                      string `json:"userName" validate:"required"`
	DailyTimestamp                int64  `json:"dailyTimestamp" validate:"required"`
	ProjectLevelAddRelationSetStr string `json:"projectLevelAddRelationSetStr" validate:"required"`
}

type DependencyRelationPair struct {
	S DependencyRelationEntity `json:"s"`
	T DependencyRelationEntity `json:"t"`
}

type DependencyRelationEntity struct {
	Id   string `json:"id"`
	Type string `json:"type"`
}
