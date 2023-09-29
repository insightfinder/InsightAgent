package main

type WebhookData struct {
	Url    string            `json:"url"`
	Alerts string            `json:"alerts"`
	Header map[string]string `json:"header"`
	Proxy  string            `json:"proxy"`
}
