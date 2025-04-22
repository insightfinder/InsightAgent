package main

import (
	"encoding/json"
	"fmt"
	"io"
	"io/ioutil"
	"log"
	"net/http"
	"net/url"
	"strings"
	"time"

	"gopkg.in/yaml.v3"
)

const HTTP_RETRY_TIMES = 10
const HTTP_RETRY_INTERVAL = 30
const ENDPOINT = "/api/v1/webhookdata"

type Config struct {
	Insightfinder struct {
		URL string `yaml:"url"`
	} `yaml:"insightfinder"`
}

func ReadConfig(filename string) (*Config, error) {
	data, err := ioutil.ReadFile(filename)
	if err != nil {
		return nil, err
	}

	config := &Config{}
	err = yaml.Unmarshal(data, config)
	if err != nil {
		return nil, err
	}

	return config, nil
}

func main() {
	config, err := ReadConfig("config.yaml")
	if err != nil {
		log.Fatalf("Error reading config: %v", err)
	}

	if config.Insightfinder.URL == "" {
		log.Fatalf("Error: URL not specified in config.yaml")
	}

	hostURL := config.Insightfinder.URL
	response, _ := SendRequest(http.MethodGet, hostURL+ENDPOINT, strings.NewReader(""), map[string]string{}, "")
	var result []WebhookData
	json.Unmarshal(response, &result)
	log.Output(2, "There are total records "+fmt.Sprint(len(result)))
	for i := 0; i < len(result); i++ {
		cur := result[i]
		serverResp, _ := SendRequest(http.MethodPost, cur.Url, strings.NewReader(cur.Alerts), cur.Header, cur.Proxy)
		log.Output(2, "Alert data has been sent to "+cur.Url)
		log.Output(2, string(serverResp))
	}
}

func SendRequest(operation string, endpoint string, form io.Reader, headers map[string]string, proxy string) ([]byte, http.Header) {
	newRequest, err := http.NewRequest(
		operation,
		endpoint,
		form,
	)
	if err != nil {
		println(err)
		return nil, nil
	}
	tr := &http.Transport{}
	proxyURL, err := url.Parse(proxy)
	if err == nil && proxy != "" {
		tr.Proxy = http.ProxyURL(proxyURL)
	}

	for k := range headers {
		newRequest.Header.Add(k, headers[k])
	}

	client := &http.Client{Transport: tr}
	var res *http.Response
	for i := 0; i < HTTP_RETRY_TIMES; i++ {
		res, err = client.Do(newRequest)
		if err == nil {
			break // Request successful, exit the loop
		}
		fmt.Printf("Error occurred: %v\n", err)
		time.Sleep(HTTP_RETRY_INTERVAL * time.Second)
		fmt.Printf("Sleep for " + fmt.Sprint(HTTP_RETRY_INTERVAL) + " seconds and retry .....")
	}
	if err != nil {
		log.Output(1, "[ERROR] HTTP connection failure after 10 times of retry.")
		log.Output(1, err.Error())
	}

	defer res.Body.Close()
	body, _ := io.ReadAll(res.Body)
	return body, res.Header
}
