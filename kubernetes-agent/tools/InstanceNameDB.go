package tools

import (
	"fmt"
	"log"
	"strings"
)

type InstanceNameDB struct {
	IndexCount   map[string]int64
	RemovedIndex map[string][]int64
	NameStorage  map[string]map[string]int64
}

func (db *InstanceNameDB) Initialize() {

	//log.Output(2, "InstanceNameDB not found. Creating new InstanceNameDB.")
	db.IndexCount = make(map[string]int64)
	db.RemovedIndex = make(map[string][]int64)
	db.NameStorage = make(map[string]map[string]int64)
}

// Merge a set of "Namespace/PodName" to the database
func (db *InstanceNameDB) Merge(namespacePodMap map[string]bool) {

	// Remove nonexistent instances
	for component, _ := range db.NameStorage {
		for storedInstance, _ := range db.NameStorage[component] {
			if _, ok := namespacePodMap[storedInstance]; !ok {
				// Add the index to the removed index queue
				if db.RemovedIndex[component] == nil {
					db.RemovedIndex[component] = make([]int64, 0)
				}
				db.RemovedIndex[component] = append(db.RemovedIndex[component], db.NameStorage[component][storedInstance])
				// Remove the instance from the name storage
				delete(db.NameStorage[component], storedInstance)
			}
		}
	}

	// Add new instances and assign index
	for instanceName, _ := range namespacePodMap {
		//Get component name
		componentName := getComponentFromPodName(instanceName)
		// Assign Index
		var currIndex int64
		if len(db.RemovedIndex[componentName]) > 0 {
			currIndex = db.RemovedIndex[componentName][0]
			db.RemovedIndex[componentName] = db.RemovedIndex[componentName][1:]
		} else {
			currIndex = db.IndexCount[componentName]
			db.IndexCount[componentName]++
		}

		// Save the index to the name storage
		if db.NameStorage[componentName] == nil {
			db.NameStorage[componentName] = make(map[string]int64)
		}
		db.NameStorage[componentName][instanceName] = currIndex
	}
	//db.Save()
}

// Load Data from disk
//func (db *InstanceNameDB) Load() bool {
//	b, e := os.ReadFile("db/InstanceNameDB.json")
//	if e != nil {
//		return false
//	}
//	e = json.Unmarshal(b, db)
//	if e != nil {
//		return false
//	}
//	return true
//}

// Save the database to the disk
//func (db *InstanceNameDB) Save() {
//	b, e := json.Marshal(db)
//	if e != nil {
//		panic(e)
//	}
//	os.WriteFile("db/InstanceNameDB.json", b, 0644)
//}

func (db *InstanceNameDB) GetStaticInstanceName(instanceName string) string {
	componentName := getComponentFromPodName(instanceName)

	index, found := db.NameStorage[componentName][instanceName]
	if !found {
		log.Output(2, fmt.Sprintf("InstanceNameDB: Skip instance: %s", instanceName))
		return ""
	}

	result := fmt.Sprintf("%s-%d", componentName, index)
	result = strings.ReplaceAll(result, "_", "-")

	if result == "insightfinder/insightfinder-0" {
		log.Output(2, "InstanceNameDB: DEBUG instance:"+instanceName)
	}

	return result
}

func (db *InstanceNameDB) Print() {
	fmt.Println("NameStorage:")
	for component, _ := range db.NameStorage {
		for instance, index := range db.NameStorage[component] {
			fmt.Println(component, instance, index)
		}
	}

	fmt.Println("IndexCount:")
	for component, index := range db.IndexCount {
		fmt.Println(component, index)
	}

	fmt.Println("RemovedIndex:")
	for component, _ := range db.RemovedIndex {
		for _, index := range db.RemovedIndex[component] {
			fmt.Println(component, index)
		}
	}
}
