package request

type QueryDataSource struct {
	Type string `json:"type"`
	UID  string `json:"uid"`
}

type QueryBody struct {
	RefId         string          `json:"refId"`
	Expr          string          `json:"expr"`
	Range         bool            `json:"range"`
	DataSource    QueryDataSource `json:"datasource"`
	DataSourceId  int             `json:"datasourceId"`
	IntervalMs    int             `json:"intervalMs"`
	MaxDataPoints int             `json:"maxDataPoints"`
}

type QueryRequestPayload struct {
	From    string      `json:"from"`
	To      string      `json:"to"`
	Queries []QueryBody `json:"queries"`
	Debug   bool        `json:"debug"`
}
