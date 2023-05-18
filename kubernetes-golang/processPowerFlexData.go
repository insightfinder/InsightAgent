package main

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"net/url"
	"regexp"
	"strconv"
	"strings"
	"time"

	"github.com/bigkevmcd/go-configparser"
)

var powerFlexSectionName = "powerFlex"
var instanceTypeRegex = `{\$instanceType}`
var idRegex = `{\$id}`
var AUTHAPI = "/api/login"

func getPFConfig(p *configparser.ConfigParser) map[string]string {
	// required fields
	var userName = ToString(GetConfigValue(p, powerFlexSectionName, "userName", true))
	var password = ToString(GetConfigValue(p, powerFlexSectionName, "password", true))
	var instanceType = ToString(GetConfigValue(p, powerFlexSectionName, "instanceType", true))
	var metricPath = ToString(GetConfigValue(p, powerFlexSectionName, "metricPath", true))
	var dataEndPoint = ToString(GetConfigValue(p, powerFlexSectionName, "dataEndPoint", true))
	var idEndPoint = ToString(GetConfigValue(p, powerFlexSectionName, "idEndPoint", true))
	var connectionUrl = ToString(GetConfigValue(p, powerFlexSectionName, "connectionUrl", true))
	// optional fields
	var metricWhitelist = ToString(GetConfigValue(p, powerFlexSectionName, "metricWhitelist", false))

	// ----------------- Process the configuration ------------------

	re := regexp.MustCompile(instanceTypeRegex)
	dataEndPoint = string(re.ReplaceAll([]byte(dataEndPoint), []byte(instanceType)))
	idEndPoint = string(re.ReplaceAll([]byte(idEndPoint), []byte(instanceType)))

	config := map[string]string{
		"userName":        userName,
		"password":        password,
		"instanceType":    instanceType,
		"metricPath":      metricPath,
		"metricWhitelist": metricWhitelist,
		"dataEndPoint":    dataEndPoint,
		"idEndPoint":      idEndPoint,
		"connectionUrl":   connectionUrl,
	}
	return config
}

func getInstanceList(config map[string]string) []string {
	// form := url.Values{}
	// getInstanceEndpoint := FormCompleteURL(
	// 	config["connectionUrl"], config["idEndPoint"],
	// )
	// // TODO: Headers currently left empty
	// var headers map[string]string
	// res := SendRequest(
	// 	http.MethodGet,
	// 	getInstanceEndpoint,
	// 	strings.NewReader(form.Encode()),
	// 	headers,
	// 	AuthRequest{
	// 		Password: config["token"],
	// 	},
	// )

	// var result []interface{}
	// json.Unmarshal(res, &result)
	// instanceList := make([]string, len(result))

	// for _, x := range result {
	// 	dict, ok := x.(map[string]interface{})
	// 	if !ok {
	// 		log.Fatal("[ERROR] Can't convert the result instance to map.")
	// 	}
	// 	instanceList = append(instanceList, ToString(dict["id"]))
	// }
	// Fake data
	instanceList := GetInstList()

	return instanceList
}

func formMetricDataPoint(metric string, value interface{}) MetricDataPoint {
	intVar, err := strconv.ParseFloat(ToString(value), 64)
	if err != nil {
		log.Fatal(err)
	}
	metricDP := MetricDataPoint{
		MetricName: metric,
		Value:      intVar,
	}
	return metricDP
}

func processDataFromInstances(curTime int64, fakeData interface{}, instance string, config map[string]string, metrics []string, data *MetricDataReceivePayload) {
	// re := regexp.MustCompile(idRegex)
	// endPoint := string(re.ReplaceAll([]byte(config["dataEndPoint"]), []byte(instance)))
	// var headers map[string]string
	// form := url.Values{}
	// res := SendRequest(
	// 	http.MethodGet,
	// 	FormCompleteURL(config["connectionUrl"], endPoint),
	// 	strings.NewReader(form.Encode()),
	// 	headers,
	// 	AuthRequest{
	// 		Password: config["token"],
	// 	},
	// )

	// timeStamp := time.Now().UnixMilli()

	// Fake data for testing

	prasedData := parseData(fakeData.(map[string]interface{}), curTime, metrics)

	instanceData, ok := data.InstanceDataMap[instance]
	if !ok {
		// Current Instance didn't exist
		instanceData = InstanceData{
			InstanceName:       instance,
			ComponentName:      "System",
			DataInTimestampMap: make(map[int64]DataInTimestamp),
		}
		data.InstanceDataMap[instance] = instanceData
	}
	instanceData.DataInTimestampMap[curTime] = prasedData
}

func parseData(data map[string]interface{}, timeStamp int64, metrics []string) DataInTimestamp {
	dataInTs := DataInTimestamp{
		TimeStamp:        timeStamp,
		MetricDataPoints: make([]MetricDataPoint, 0),
	}
	var stack Stack
	for _, metric := range metrics {
		metric = strings.ReplaceAll(metric, " ", "")
		stack.Push(MetricStack{
			Metric: data[metric],
			Prefix: metric,
		})
	}
	for {
		if stack.IsEmpty() {
			break
		}
		metricElem, _ := stack.Pop()
		curVal := metricElem.Metric
		curPrefix := metricElem.Prefix
		switch curVal.(type) {
		case string:
			dataInTs.MetricDataPoints = append(dataInTs.MetricDataPoints, formMetricDataPoint(curPrefix, curVal))
		case float64, int64:
			dataInTs.MetricDataPoints = append(dataInTs.MetricDataPoints, formMetricDataPoint(curPrefix, fmt.Sprint(curVal)))
		case interface{}:
			curMetricMap, success := curVal.(map[string]interface{})
			if !success {
				log.Fatal("[ERROR] Can't parse the metric " + curPrefix)
			}
			for k, v := range curMetricMap {
				stack.Push(MetricStack{
					Metric: v,
					Prefix: curPrefix + "." + k,
				})
			}
		default:
			log.Fatal("[ERROR] Wrong type input from the data")
		}
	}
	return dataInTs
}

func getToken(config map[string]string) string {
	authEndPoint := FormCompleteURL(
		config["connectionUrl"], AUTHAPI,
	)
	form := url.Values{}
	var headers map[string]string

	token := string(SendRequest(
		http.MethodGet,
		authEndPoint,
		strings.NewReader(form.Encode()),
		headers,
		AuthRequest{
			UserName: config["userName"],
			Password: config["password"],
		},
	))

	return token
}

func PowerFlexDataStream(p *configparser.ConfigParser, IFconfig map[string]interface{}) MetricDataReceivePayload {
	config := getPFConfig(p)
	// token := getToken(config)
	// fake data
	token := "test"
	log.Output(1, "[LOG] Successful get the token from Gateway API")
	log.Output(1, "[LOG] token: "+token)
	config["token"] = token
	instances := getInstanceList(config)

	projectName := ToString(IFconfig["projectName"])
	userName := ToString(IFconfig["userName"])
	data := MetricDataReceivePayload{
		ProjectName:     projectName,
		UserName:        userName,
		InstanceDataMap: make(map[string]InstanceData),
	}
	metrics, err := ReadLines("conf.d/" + config["metricPath"])
	if err != nil {
		log.Fatal(err)
	}
	res := []byte(`
	[{
        "unusedCapacityInKb": 26177490944,
        "currentTickerValue": 65806799,
        "persistentChecksumCapacityInKb": 18309120,
        "numOfVolumes": 15,
        "totalReadBwc": {
            "numSeconds": 0,
            "totalWeightInKb": 0,
            "numOccured": 0
        }
},
{
        "unusedCapacityInKb": 26177488896,
        "currentTickerValue": 65806865,
        "persistentChecksumCapacityInKb": 18309120,
        "numOfVolumes": 15,
        "totalReadBwc": {
            "numSeconds": 5,
            "totalWeightInKb": 36,
            "numOccured": 7
        }
},
{
        "unusedCapacityInKb": 26177488896,
        "currentTickerValue": 65806925,
        "persistentChecksumCapacityInKb": 18309120,
        "numOfVolumes": 15,
        "totalReadBwc": {
            "numSeconds": 0,
            "totalWeightInKb": 0,
            "numOccured": 0
        }
},
{
        "unusedCapacityInKb": 26177488896,
        "currentTickerValue": 65806963,
        "persistentChecksumCapacityInKb": 18309120,
        "numOfVolumes": 15,
        "totalReadBwc": {
            "numSeconds": 5,
            "totalWeightInKb": 2687,
            "numOccured": 87
        }

},
{

        "unusedCapacityInKb": 26177488896,
        "currentTickerValue": 65807252,
        "persistentChecksumCapacityInKb": 18309120,
        "numOfVolumes": 15,
        "totalReadBwc": {
            "numSeconds": 0,
            "totalWeightInKb": 0,
            "numOccured": 0
        }

}]
	`)
	var result []interface{}
	json.Unmarshal(res, &result)
	timeStamp := time.Now().UnixMilli()
	for i := 0; i < 5; i++ {
		timeStamp += +300000
		processDataFromInstances(timeStamp, result[i], instances[i], config, metrics, &data)
		// time.Sleep(time.Second * 5)
	}
	return data
}
