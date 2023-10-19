package tools

import (
	"encoding/json"
	"fmt"
	"log"
	"os"
	"reflect"
	"regexp"
)

func ToString(inputVar interface{}) string {
	if inputVar == nil {
		return ""
	}
	return fmt.Sprint(inputVar)
}

func ToBool(inputVar interface{}) bool {
	if inputVar == nil {
		return false
	}
	mtype := reflect.TypeOf(inputVar)
	if fmt.Sprint(mtype) == "bool" {
		return inputVar.(bool)
	}
	panic("[ERROR] Wrong input type. Can not convert current input to boolean.")
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

func PrintStruct(v any, needPrint bool, fileName string) {
	jsonBytes, err := json.MarshalIndent(v, "", "  ")
	if err != nil {
		log.Fatalf("JSON marshaling failed: %s", err)
	}
	if needPrint {
		fmt.Println(string(jsonBytes))
	}
	err = os.WriteFile("PrintStruct-"+fileName+".json", jsonBytes, 0644)
	if err != nil {
		log.Fatalf("Writing to file failed: %s", err)
	}
}

func removePVCNameSuffix(PVCName string) string {
	re := regexp.MustCompile(`-\d+$`)
	return re.ReplaceAllString(PVCName, "")
}

func removePodNameSuffix(podName string) string {
	regex := regexp.MustCompile(`(-[a-z0-9]{8,10}-[a-z0-9]{5}|-\d)$`)
	return regex.ReplaceAllString(podName, "")
}
