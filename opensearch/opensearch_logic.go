package main

import (
	"bytes"
	"crypto/tls"
	"crypto/x509"
	"encoding/json"
	"io"
	"io/ioutil"
	"net/http"
	"time"

	"github.com/bigkevmcd/go-configparser"
	golangif "github.com/insightfinder/InsightAgent/tree/master/golang-IF"
)

const OpenSearchSection = "opensearch"

func sendRequestViaMTLS(
	operation string,
	endpoint string,
	certificatePath string,
	privateKeyPath string,
	rootCertPath string,
	requestBody io.Reader,
	headers map[string]string,
	auth golangif.AuthRequest) ([]byte, http.Header) {
	newRequest, err := http.NewRequest(
		operation,
		endpoint,
		requestBody,
	)
	if auth.Password != "" {
		newRequest.SetBasicAuth(auth.UserName, auth.Password)
	}
	if err != nil {
		panic(err)
	}

	for k := range headers {
		newRequest.Header.Add(k, headers[k])
	}
	var client *http.Client
	caCertPool := x509.NewCertPool()
	// Load root CA certificate if the server is using self-signed CA.
	if rootCertPath != "" {
		caCert, err := ioutil.ReadFile(rootCertPath)
		if err != nil {
			panic(err)
		}
		caCertPool.AppendCertsFromPEM(caCert)
	}

	clientCert, err := tls.LoadX509KeyPair(certificatePath, privateKeyPath)
	if err != nil {
		panic(err)
	}

	tlsConfig := &tls.Config{
		Certificates: []tls.Certificate{clientCert},
		RootCAs:      caCertPool,
		// Set to true only if the server's certificate is self-signed or not in a CA store
		InsecureSkipVerify: false,
	}

	client = &http.Client{
		Transport: &http.Transport{
			TLSClientConfig: tlsConfig,
		},
	}

	res, err := client.Do(newRequest)
	if err != nil {
		panic(err)
	}

	defer res.Body.Close()
	body, _ := io.ReadAll(res.Body)

	return body, res.Header
}
func readOpensearchConfig(p *configparser.ConfigParser) map[string]string {
	// required fields
	var server_url = golangif.ToString(golangif.GetConfigValue(p, OpenSearchSection, "server_url", true))
	var cert_file_path = golangif.ToString(golangif.GetConfigValue(p, OpenSearchSection, "cert_file_path", true))
	var key_file_path = golangif.ToString(golangif.GetConfigValue(p, OpenSearchSection, "key_file_path", true))
	var root_ca_path = golangif.ToString(golangif.GetConfigValue(p, OpenSearchSection, "root_ca_path", true))
	var instnace_name_field = golangif.ToString(golangif.GetConfigValue(p, OpenSearchSection, "instnace_name_field", true))
	var timestamp_field = golangif.ToString(golangif.GetConfigValue(p, OpenSearchSection, "timestamp_field", true))
	var query = golangif.ToString(golangif.GetConfigValue(p, OpenSearchSection, "query", true))
	var query_endpoint = golangif.ToString(golangif.GetConfigValue(p, OpenSearchSection, "query_endpoint", false))
	var query_format = golangif.ToString(golangif.GetConfigValue(p, OpenSearchSection, "query_format", false))

	if query_endpoint == "" {
		query_endpoint = "_plugins/_sql"
	}
	if query_format == "" {
		query_format = "jdbc"
	}

	config := map[string]string{
		"server_url":          server_url,
		"cert_file_path":      cert_file_path,
		"key_file_path":       key_file_path,
		"root_ca_path":        root_ca_path,
		"instnace_name_field": instnace_name_field,
		"timestamp_field":     timestamp_field,
		"query":               query,
		"query_endpoint":      query_endpoint,
		"query_format":        query_format,
	}
	return config
}

func getOpenSearchData(config map[string]string) []byte {
	endpoint := config["server_url"]
	cert_file_path := config["cert_file_path"]
	key_file_path := config["key_file_path"]
	root_ca_path := config["root_ca_path"]
	query := config["query"]
	query_endpoint := config["query_endpoint"]
	query_format := config["query_format"]

	header := map[string]string{}
	header["Content-Type"] = "application/json"
	if query_format != "" {
		header["format"] = query_format
	}
	queryRequestBody := QueryRequest{
		Query: query,
	}

	jsonBody, err := json.Marshal(queryRequestBody)
	if err != nil {
		panic(err)
	}
	completeEndpoint := golangif.FormCompleteURL(endpoint, query_endpoint)
	responseBody, _ := sendRequestViaMTLS(http.MethodPost, completeEndpoint, cert_file_path, key_file_path, root_ca_path,
		bytes.NewBuffer(jsonBody), header, golangif.AuthRequest{})
	println(string(responseBody))

	sampleResponse := []byte(`
	{
		"_shards": {
		  "total": 5,
		  "failed": 0,
		  "successful": 5,
		  "skipped": 0
		},
		"hits": {
		  "hits": [{
			  "_index": "accounts",
			  "_type": "account",
			  "_source": {
				"firstname": "Nanette",
				"age": 1690232200,
				"lastname": "Bates"
			  },
			  "_id": "13",
			  "sort": [
				28
			  ],
			  "_score": null
			},
			{
			  "_index": "accounts",
			  "_type": "account",
			  "_source": {
				"firstname": "Amber",
				"age": 1690732200,
				"lastname": "Duke"
			  },
			  "_id": "1",
			  "sort": [
				32
			  ],
			  "_score": null
			}
		  ],
		  "total": {
			"value": 4,
			"relation": "eq"
		  },
		  "max_score": null
		},
		"took": 100,
		"timed_out": false
	  }`)
	return sampleResponse
}

func processOSData(config map[string]string, response []byte) (logData []golangif.LogData) {
	var data JSONResponse
	json.Unmarshal(response, &data)
	for _, v := range data.Hits.HitsItem {
		eventData := v.Source
		instanceField := config["instnace_name_field"]
		timestampField := config["timestamp_field"]

		// TODO: Need to parse the timestamp based on the real ts format.
		ts := int64(eventData[timestampField].(float64))
		timeStamp := time.Unix(ts, 0).UnixMilli()
		instanceName := golangif.ToString(eventData[instanceField])
		logData = append(logData, golangif.LogData{
			TimeStamp: timeStamp,
			Tag:       instanceName,
			Data:      eventData,
		})
	}
	return
}
