package host_mapper

import (
	"github.com/golang-collections/collections/set"
	"gorm.io/driver/sqlite"
	"gorm.io/gorm"
	"kubernetes-agent/host_mapper/models"
	"log/slog"
)

type HostMapper struct {
	db *gorm.DB
}

func (hostMapper *HostMapper) Initialize() {

	// Database Initialization
	db, err := gorm.Open(sqlite.Open("storage/data.db"), &gorm.Config{})
	if err != nil {
		slog.Error("Failed to connect database.")
	}

	// Migrate the schema
	err = db.AutoMigrate(&models.HostMapping{})
	if err != nil {
		slog.Error("Failed to migrate database:", err)
	}
	hostMapper.db = db
}

func (hostMapper *HostMapper) GetAvailIndexes(maxIndex int) []int {
	// get all Indexes in HostMapping table
	// SELECT IndexID FROM HostMapping
	var existingIndexesArray []int
	hostMapper.db.Model(&models.HostMapping{}).Select("IndexID").Find(&existingIndexesArray)

	// Convert to Set
	existingIndexes := set.New()
	for _, index := range existingIndexesArray {
		existingIndexes.Insert(index)
	}

	// Generate an array from 0 to maxIndex
	allIndexes := set.New()
	for i := 0; i < maxIndex; i++ {
		allIndexes.Insert(i)
	}

	// Get available indexes using Difference
	availIndexesSet := allIndexes.Difference(existingIndexes)

	// Convert Set to Array
	availIndexes := make([]int, availIndexesSet.Len())
	availIndexesSet.Do(func(elem interface{}) {
		// Assert the element's type to int
		if value, ok := elem.(int); ok {
			availIndexes = append(availIndexes, value)
		}
	})

	return availIndexes
}
