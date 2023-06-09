package main

import (
	"database/sql"
	"fmt"
	"io/fs"
	"log"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"github.com/bigkevmcd/go-configparser"
	_ "github.com/mattn/go-sqlite3"
)

func getLocalFileConfig(p *configparser.ConfigParser) map[string]string {
	// required fields
	var path = ToString(GetConfigValue(p, LocalFileSection, "path", true))
	var timeStampField = ToString(GetConfigValue(p, LocalFileSection, "timeStampField", true))
	var tableName = ToString(GetConfigValue(p, LocalFileSection, "tableName", true))

	// ----------------- Process the configuration ------------------
	var instanceNameField = ToString(GetConfigValue(p, LocalFileSection, "instanceNameField", false))
	var subDirectToSkip = ToString(GetConfigValue(p, LocalFileSection, "subDirectToSkip", false))

	config := map[string]string{
		"path":              path,
		"timeStampField":    timeStampField,
		"tableName":         tableName,
		"instanceNameField": instanceNameField,
		"subDirectToSkip":   subDirectToSkip,
	}
	return config
}

func readDBData(config map[string]string, filePath string, IFConfig map[string]interface{}, wg *sync.WaitGroup) {
	defer wg.Done()
	println("start of the job" + filePath)
	var ts int64
	var instanceName string
	var res []LogData
	tsCol := config["timeStampField"]
	instanceCol := config["instanceNameField"]
	tableName := config["tableName"]

	sqliteDatabase, _ := sql.Open("sqlite3", filePath)
	defer sqliteDatabase.Close()
	// only select a small amount of data.
	// use paging
	rows, err := sqliteDatabase.Query("SELECT * FROM " + tableName + ";")
	if err != nil {
		log.Fatal(err)
	}
	defer rows.Close()
	columns, err := rows.Columns()
	if err != nil {
		panic(err.Error())
	}

	// Create a slice of interface{} to hold the column values
	values := make([]interface{}, len(columns))
	for i := range values {
		var value interface{}
		values[i] = &value
	}

	// Iterate over the rows and scan the column values dynamically
	for rows.Next() {
		err := rows.Scan(values...)
		if err != nil {
			panic(err.Error())
		}
		// Create a map to hold the row data
		rowData := make(map[string]interface{})

		// Iterate over the column names and corresponding values
		for i, col := range columns {
			// Get the column value for the current row
			value := *(values[i].(*interface{}))
			// Add the column name and value to the map
			rowData[col] = value
			if col == tsCol {
				switch value := value.(type) {
				case time.Time:
					parsedTime := value
					ts = parsedTime.UnixMilli()
				case string:
					parsedTime, err := time.Parse(value, value)
					if err != nil {
						panic(err.Error())
					}
					ts = parsedTime.UnixMilli()
				case int64:
					ts = time.Unix(value, 0).UnixMilli()
				case float64:
					ts = time.Unix(int64(value), 0).UnixMilli()
				}
			}
			if col == instanceCol {
				instanceName = ToString(value)
			}
		}
		if instanceName == "" {
			instanceName = "NO_INSTANCE_NAME"
		}
		res = append(res, LogData{
			TimeStamp: ts,
			Tag:       instanceName,
			Data:      rowData,
		})
	}
	log.Output(1, "The count of the record is: "+fmt.Sprint(len(res)))
	sendLogData(res, IFConfig)
	log.Output(1, "[LOG] Finsihed data loading from: "+filePath)
}

func LocalLogDataStream(p *configparser.ConfigParser, IFConfig map[string]interface{}) {
	config := getLocalFileConfig(p)
	fileList := []string{}

	subDirToSkip := strings.Split(config["subDirectToSkip"], ",")
	filepath.Walk(config["path"], func(path string, info fs.FileInfo, err error) error {
		if err != nil {
			fmt.Printf("prevent panic by handling failure accessing a path %q: %v\n", path, err)
			return err
		}
		if info.IsDir() && contains(subDirToSkip, info.Name()) {
			fmt.Printf("skipping a dir without errors: %+v \n", info.Name())
			return filepath.SkipDir
		}
		if !info.IsDir() && strings.HasSuffix(info.Name(), ".db") {
			fileList = append(fileList, path)
		}
		return nil
	})
	waitGroup := new(sync.WaitGroup)
	for _, filePath := range fileList {
		waitGroup.Add(1)
		go readDBData(config, filePath, IFConfig, waitGroup)
	}
	waitGroup.Wait()
}
