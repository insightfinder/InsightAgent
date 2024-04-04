package host_mapper

import (
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

func (hostMapper *HostMapper) RemovedHostsIfNotExist(hosts *[]string) {
	var toBeDeletedHosts []string
	hostMapper.db.Model(&models.HostMapping{}).Where("host NOT IN ?", *hosts).Pluck("host", &toBeDeletedHosts)

	for _, host := range toBeDeletedHosts {
		slog.Debug("Removed host:", host)
	}
	hostMapper.db.Model(&models.HostMapping{}).Where("host NOT IN ?", *hosts).Delete(&models.HostMapping{})
}

func (hostMapper *HostMapper) InsertHosts(hosts *[]string) {
	var existingIndexes []int
	var existingHosts []string

	// Assume all indexes and all hosts are available
	availIndexes := make(map[int]bool)
	availIndexesList := make([]int, 0)
	newHosts := make(map[string]bool)
	for i := 0; i < len(*hosts); i++ {
		availIndexes[i] = true
		newHosts[(*hosts)[i]] = true
	}

	// Get all used hosts and indexes from the db.
	hostMapper.db.Model(&models.HostMapping{}).Select("host,index_id").Pluck("index_id", &existingIndexes).Pluck("host", &existingHosts)

	// Mark them as false in availIndexes
	for _, index := range existingIndexes {
		availIndexes[index] = false
	}

	// Convert available indexes to a list
	for index, isAvailable := range availIndexes {
		if isAvailable {
			availIndexesList = append(availIndexesList, index)
		}
	}

	// Filter out existing hosts
	for _, existingHost := range existingHosts {
		newHosts[existingHost] = false
	}

	// Assign indexes to hosts
	for host, isNewHost := range newHosts {
		if isNewHost {
			slog.Info("Prepare to insert new host:", host)

			// Get an index from avail index
			newIndex := availIndexesList[0]
			availIndexesList = availIndexesList[1:]

			slog.Info("Assign index", newIndex, "to host: ", host)
			newHosts[host] = false
		}
	}
}
