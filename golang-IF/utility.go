package golangif

import (
	"fmt"
	"log"
	"net/url"
	"os"
	"path"
	"path/filepath"
	"reflect"
	"strconv"
	"strings"

	"github.com/bigkevmcd/go-configparser"
)

func AbsFilePath(filename string) string {
	if filename == "" {
		filename = ""
	}
	curdir, err := os.Getwd()
	if err != nil {
		panic(err)
	}
	mydir, err := filepath.Abs(curdir)
	if err != nil {
		panic(err)
	}
	return filepath.Join(mydir, filename)
}

func GetConfigValue(p *configparser.ConfigParser, section string, param string, required bool) interface{} {
	result, err := p.Get(section, param)
	if err != nil && required {
		panic(err)
	}
	if result == "" && required {
		panic("[ERROR] InsightFinder configuration [" + param + "] is required!")
	}
	return result
}

func FormCompleteURL(link string, endpoint string) string {
	postUrl, err := url.Parse(link)
	if err != nil {
		log.Output(1, "[ERROR] Fail to pares the URL. Please check your config.")
		panic(err)
	}
	postUrl.Path = path.Join(postUrl.Path, endpoint)
	return postUrl.String()
}

func ToString(inputVar interface{}) string {
	if inputVar == nil {
		return ""
	}
	return fmt.Sprint(inputVar)
}

func ToBool(inputVar interface{}) (boolValue bool) {
	if inputVar == nil {
		return false
	}
	switch castedVal := inputVar.(type) {
	case string:
		var err error
		boolValue, err = strconv.ParseBool(castedVal)
		if err != nil {
			panic("[ERROR] Wrong input type. Can not convert current input to boolean.")
		}
	case bool:
		boolValue = castedVal
	}
	return boolValue
}

func ToInt(inputVar interface{}) int {
	if inputVar == nil {
		return 0
	}
	mtype := reflect.TypeOf(inputVar)
	if fmt.Sprint(mtype) == "int" {
		return inputVar.(int)
	}
	panic("[ERROR] Wrong input type. Can not convert current input to int.")
}

// Need to test the functionality. Only support primitive type.
func Contains(s []interface{}, str interface{}) bool {
	for _, v := range s {
		if v == str {
			return true
		}
	}
	return false
}

// ------------------ Project Type transformation ------------------------

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
