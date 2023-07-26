package main

type QueryRequest struct {
	Query string `json:"query" validate:"required"`
}

type Schema struct {
	Name string `json:"name"`
	Type string `json:"type"`
}

type JDBCResponse struct {
	Schema   []Schema `json:"schema"`
	Total    uint     `json:"total"`
	Datarows [][]any  `json:"datarows"`
	Size     uint     `json:"size"`
	Status   uint     `json:"status"`
}

type Shards struct {
	Total      uint `json:"total"`
	Failed     uint `json:"failed"`
	Successful uint `json:"successful"`
	Skipped    uint `json:"skipped"`
}
type HitsItem struct {
	Index  string         `json:"_index"`
	Type   string         `json:"_type"`
	Source map[string]any `json:"_source"`
	Id     string         `json:"_id"`
	Sort   []int          `json:"sort"`
	Score  any            `json:"_score"`
}

type HitsTotal struct {
	Value    int    `json:"value"`
	Relation string `json:"relation"`
}

type Hits struct {
	HitsItem  []HitsItem `json:"hits"`
	Max_score any        `json:"max_score"`
	Total     HitsTotal  `json:"total"`
}
type JSONResponse struct {
	Shards    Shards `json:"_shards"`
	Hits      Hits   `json:"hits"`
	Took      uint   `json:"took"`
	Timed_out bool   `json:"timed_out"`
}
