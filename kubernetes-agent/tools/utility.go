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

func getComponentFromPodName(podName string) string {
	// split the pod name with '-' and remove the last part to be the component name
	// e.g. "prometheus-k8s-0" -> "prometheus-k8s"
	rMatchGeneralDeployments, _ := regexp.Compile("^(.*?)(-[^-]*){1,2}$")
	rMatchEndOfStringDashDigits, _ := regexp.Compile("-\\d+$")
	if rMatchEndOfStringDashDigits.MatchString(podName) {
		return rMatchEndOfStringDashDigits.ReplaceAllString(podName, "")
	} else {
		return rMatchGeneralDeployments.ReplaceAllString(podName, "$1")
	}

}

func PrintStruct(v any, needPrint bool) {
	jsonBytes, err := json.MarshalIndent(v, "", "  ")
	if err != nil {
		log.Fatalf("JSON marshaling failed: %s", err)
	}
	if needPrint {
		fmt.Println(string(jsonBytes))
	}
	err = os.WriteFile("PrintStruct.json", jsonBytes, 0644)
	if err != nil {
		log.Fatalf("Writing to file failed: %s", err)
	}
}

func PrintSet(m map[string]bool) {
	for k, _ := range m {
		fmt.Print(k)
		fmt.Println()
	}
}
