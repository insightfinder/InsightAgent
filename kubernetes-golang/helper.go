package main

import (
	"fmt"
	"io"
	"log"
	"net/http"
	"net/url"
	"path"
	"path/filepath"
	"reflect"
	"strings"

	"github.com/bigkevmcd/go-configparser"
)

func GetConfigValue(p *configparser.ConfigParser, section string, param string, required bool) interface{} {
	result, err := p.Get(section, param)
	if err != nil && required {
		log.Fatal(err)
	}
	if result == "" && required {
		log.Fatal("[ERROR] InsightFinder configuration [", param, "] is required!")
	}
	return result
}

func FormCompleteURL(link string, endpoint string) string {
	postUrl, err := url.Parse(link)
	if err != nil {
		log.Output(1, "[ERROR] Fail to pares the URL. Please check your config.")
		log.Fatal(err)
	}
	postUrl.Path = path.Join(postUrl.Path, endpoint)
	return postUrl.String()
}

func IsString(inputVar interface{}) bool {
	mtype := reflect.TypeOf(inputVar)
	return fmt.Sprint(mtype) == "string"
}

func IsInterface(inputVar interface{}) bool {
	mtype := reflect.TypeOf(inputVar)
	return fmt.Sprint(mtype) == "interface"
}

func SendMetricDataToIF(data interface{}, config map[string]interface{}) {
	println("send Data to IF")
}

func SendRequest(operation string, endpoint string, form io.Reader, headers map[string]string) []byte {
	newRequest, err := http.NewRequest(
		operation,
		endpoint,
		form,
	)
	if err != nil {
		log.Fatal(err)
	}

	for k := range headers {
		newRequest.Header.Add(k, headers[k])
	}

	client := &http.Client{}
	res, err := client.Do(newRequest)
	if err != nil {
		log.Fatal(err)
	}

	defer res.Body.Close()
	body, _ := io.ReadAll(res.Body)

	return body
}

func AbsFilePath(filename string) string {
	if filename == "" {
		filename = ""
	}
	absFilePath, err := filepath.Abs(filename)
	if err != nil {
		log.Fatal(err)
	}
	return absFilePath
}

func ProjectTypeToAgentType(projectType string, isReplay bool) string {
	if isReplay {
		if strings.Contains(projectType, "METRIC") {
			return "MetricFile"
		} else {
			return "LogFile"
		}
	}
	return "Custom"
}

func IsValidProjectType(projectType string) bool {
	switch projectType {
	case
		"METRIC",
		"METRICREPLAY",
		"LOG",
		"LOGREPLAY",
		"INCIDENT",
		"INCIDENTREPLAY",
		"ALERT",
		"ALERTREPLAY",
		"DEPLOYMENT",
		"DEPLOYMENTREPLAY",
		"TRACE",
		"TRAVEREPLAY":
		return true
	}
	return false
}

func ProjectTypeToDataType(projectType string) string {
	switch projectType {
	case "METRIC":
		return "Metric"
	case "METRICREPLAY":
		return "Metric"
	case "ALERT":
		return "Alert"
	case "INCIDENT":
		return "Incident"
	case "DEPLOYMENT":
		return "Deployment"
	case "TRACE":
		return "Trace"
	default:
		return "Log"
	}
}

type MetricStack struct {
	Metric interface{}
	Prefix string
}

// -------------------- The stack type data structure ---------------------

type Stack []MetricStack

// IsEmpty: check if stack is empty
func (s *Stack) IsEmpty() bool {
	return len(*s) == 0
}

// Push a new value onto the stack
func (s *Stack) Push(stk MetricStack) {
	*s = append(*s, stk) // Simply append the new value to the end of the stack
}

// Remove and return top element of stack. Return false if stack is empty.
func (s *Stack) Pop() (MetricStack, bool) {
	if s.IsEmpty() {
		return MetricStack{}, false
	} else {
		index := len(*s) - 1   // Get the index of the top most element.
		element := (*s)[index] // Index into the slice and obtain the element.
		*s = (*s)[:index]      // Remove it from the stack by slicing it off.
		return element, true
	}
}
