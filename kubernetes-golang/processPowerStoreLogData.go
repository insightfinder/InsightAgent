package main

import (
	"encoding/json"
	"github.com/bigkevmcd/go-configparser"
	"io/ioutil"
	"log"
)

func getPStoreLogConfig(p *configparser.ConfigParser) map[string]string {
	// required fields
	var userName = ToString(GetConfigValue(p, PowerStoreLogSectionName, "userName", true))
	var password = ToString(GetConfigValue(p, PowerStoreLogSectionName, "password", true))
	var logPath = ToString(GetConfigValue(p, PowerStoreSectionName, "logPath", true))
	var connectionUrl = ToString(GetConfigValue(p, PowerStoreSectionName, "connectionUrl", true))
	var instanceNameField = ToString(GetConfigValue(p, PowerStoreSectionName, "instanceNameField", true))
	var timeStampField = ToString(GetConfigValue(p, PowerStoreSectionName, "timeStampField", true))

	// ----------------- Process the configuration ------------------

	config := map[string]string{
		"userName":          userName,
		"password":          password,
		"logPath":           logPath,
		"connectionUrl":     connectionUrl,
		"timeStampField":    timeStampField,
		"instanceNameField": instanceNameField,
	}
	return config
}

func getPowerStoreLogData(config map[string]string) []interface{} {
	// TODO: read from local json replace with api call
	// The key is the instance name and the
	filePath := "mockdata/audit_event.json"
	data, err := ioutil.ReadFile(filePath)
	if err != nil {
		log.Fatal(err)
	}
	var result []interface{}

	json.Unmarshal([]byte(data), &result)
	return result
}

func PowerStoreLogStream(p *configparser.ConfigParser, IFConfig map[string]interface{}) LogDataReceivePayload {
	pStoreConfig := getPStoreLogConfig(p)
	projectName := ToString(IFConfig["projectName"])
	userName := ToString(IFConfig["userName"])

	data := LogDataReceivePayload{
		ProjectName: projectName,
		UserName:    userName,
	}

	//pStoreConfig["token"] = getAuthToken(pStoreConfig)

	objectArray := getPowerStoreMetricData(pStoreConfig)
	return data
}
