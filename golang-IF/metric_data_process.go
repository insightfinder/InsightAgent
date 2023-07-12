package golangif

import (
	"encoding/json"
	"fmt"
	"io/ioutil"
	"log"
	"os"
	"strconv"
	"strings"
	"time"
)

func GetEndpointMetricMapping(path string) (map[string][]string, error) {
	jsonFile, err := os.Open(AbsFilePath("conf.d/" + path))
	if err != nil {
		return nil, err
	}
	byteValue, err := ioutil.ReadAll(jsonFile)
	if err != nil {
		return nil, err
	}
	var endPointMapping map[string][]string
	json.Unmarshal(byteValue, &endPointMapping)
	return endPointMapping, nil
}

func FormMetricDataPoint(metric string, value interface{}) (MetricDataPoint, error) {
	intVar, err := strconv.ParseFloat(ToString(value), 64)
	if err != nil {
		return MetricDataPoint{}, err
	}
	metricDP := MetricDataPoint{
		MetricName: metric,
		Value:      intVar,
	}
	return metricDP, nil
}

func ProcessArrayDataFromEndPoint(objArrary []interface{}, metricList []string, timeStampField string, instanceNameField string, data *MetricDataReceivePayload) {
	for index, obj := range objArrary {
		object, success := obj.(map[string]interface{})
		if !success {
			panic("[ERROR] Can't parse the object array with index: " +
				fmt.Sprint(index))
		}
		// Get timeStamp in epoch milli-second format
		var tsInInt64 int64
		switch tsAfterCast := object[timeStampField].(type) {
		case int64:
			tsInInt64 = tsAfterCast
		case float64:
			tsInInt64 = int64(tsAfterCast)
		case string:
			parsedTime, err := time.Parse(tsAfterCast, tsAfterCast)
			if err != nil {
				panic(err.Error())
			}
			tsInInt64 = parsedTime.Unix()
		}
		if tsInInt64 == 0 {
			panic("Can't get timeStamp from timestamp field" + object[timeStampField].(string))
		}
		timeStamp := time.Unix(tsInInt64, 0).UnixMilli()

		prasedData := ParseData(object, timeStamp, metricList)
		instance, success := object[instanceNameField].(string)
		if !success {
			panic("[ERROR] Failed to get instance name from the field: " + instanceNameField)
		}
		instanceData, ok := data.InstanceDataMap[instance]
		if !ok {
			// Current Instance didn't exist
			instanceData = InstanceData{
				InstanceName:       instance,
				ComponentName:      instance,
				DataInTimestampMap: make(map[int64]DataInTimestamp),
			}
			data.InstanceDataMap[instance] = instanceData
		}
		instanceData.DataInTimestampMap[timeStamp] = prasedData
	}
}

func ParseData(data map[string]interface{}, timeStamp int64, metrics []string) DataInTimestamp {
	dataInTs := DataInTimestamp{
		TimeStamp:        timeStamp,
		MetricDataPoints: make([]MetricDataPoint, 0),
	}
	var stack Stack
	if len(metrics) == 0 {
		// if length of the metrics list is 0, get all metrics.
		for key, value := range data {
			stack.Push(MetricStack{
				Metric: value,
				Prefix: key,
			})
		}
	} else {
		for _, metric := range metrics {
			metric = strings.ReplaceAll(metric, " ", "")
			stack.Push(MetricStack{
				Metric: data[metric],
				Prefix: metric,
			})
		}
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
			value, err := FormMetricDataPoint(curPrefix, curVal)
			if err == nil {
				dataInTs.MetricDataPoints = append(dataInTs.MetricDataPoints, value)
			} else {
				log.Output(1, err.Error())
				log.Output(1, "Failed to cast value"+fmt.Sprint(curVal)+"to number")
			}
		case float64, int64:
			value, err := FormMetricDataPoint(curPrefix, fmt.Sprint(curVal))
			if err == nil {
				dataInTs.MetricDataPoints = append(dataInTs.MetricDataPoints, value)
			} else {
				log.Output(1, err.Error())
				log.Output(1, "Failed to cast value"+curVal.(string)+"to number")
			}
		case interface{}:
			curMetricMap, success := curVal.(map[string]interface{})
			if !success {
				panic("[ERROR] Can't parse the metric " + curPrefix)
			}
			for k, v := range curMetricMap {
				stack.Push(MetricStack{
					Metric: v,
					Prefix: curPrefix + "." + k,
				})
			}
		default:
			panic("[ERROR] Wrong type input from the data. Key:" +
				curPrefix + " ;Value: " + fmt.Sprint(curVal))
		}
	}
	return dataInTs
}

// -------------------- The stack type data structure ---------------------
type MetricStack struct {
	Metric interface{}
	Prefix string
}

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
