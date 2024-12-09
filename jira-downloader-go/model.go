package main

type JiraSearchResponse struct {
	Issues     []any `json:"issues"`
	StartAt    int   `json:"startAt"`
	MaxResults int   `json:"maxResults"`
	Total      int   `json:"total"`
}

type JiraCommentResponse struct {
	Comments []any `json:"comments"`
}
