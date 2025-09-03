package worker

import (
	"encoding/json"
	"fmt"
	"os"
	"time"

	"github.com/sirupsen/logrus"
)

// ------- Worker methods for testing functionality -------

// Enable test mode for development/testing
func (w *Worker) EnableTestMode() {
	w.testMode = true
	logrus.Info("Test mode enabled - data will be saved to files instead of sent to InsightFinder")
}

// Test Positron API functionality
func (w *Worker) TestPositronAPIs() error {
	logrus.Info("Testing Positron API functionality")

	// Test endpoints API
	endpoints, err := w.positronService.GetEndpoints()
	if err != nil {
		return fmt.Errorf("failed to get endpoints: %v", err)
	}
	logrus.Infof("Retrieved %d endpoints", len(endpoints))

	// Test devices API
	devices, err := w.positronService.GetDevices()
	if err != nil {
		return fmt.Errorf("failed to get devices: %v", err)
	}
	logrus.Infof("Retrieved %d devices", len(devices))

	// Test alarms API
	alarms, err := w.positronService.GetAlarms()
	if err != nil {
		return fmt.Errorf("failed to get alarms: %v", err)
	}
	logrus.Infof("Retrieved %d alarms", len(alarms))

	return nil
}

// Create test file for saving data
func (w *Worker) createTestFile(prefix string) (*os.File, error) {
	timestamp := time.Now().Format("20060102_150405")
	filename := fmt.Sprintf("%s_%s.json", prefix, timestamp)
	return os.Create(filename)
}

// Save test data to file
func (w *Worker) saveTestData(filename string, data interface{}) error {
	file, err := os.Create(filename)
	if err != nil {
		return err
	}
	defer file.Close()

	encoder := json.NewEncoder(file)
	encoder.SetIndent("", "  ")
	return encoder.Encode(data)
}
