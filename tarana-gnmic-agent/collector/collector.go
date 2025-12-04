package collector

import (
	"encoding/csv"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"

	"github.com/sirupsen/logrus"
)

// RNDevice represents a Remote Node device with its metrics
type RNDevice struct {
	Hostname    string
	Source      string
	DeviceID    string
	Measurement string
	Timestamp   time.Time
	DLSNR       string
	ULSNR       string
	PathLoss    string
	RFRange     string
	RXSignal0   string
	RXSignal1   string
	RXSignal2   string
	RXSignal3   string
}

// BNDevice represents a Base Node device with its metrics
type BNDevice struct {
	Hostname          string
	Source            string
	Measurement       string
	Timestamp         time.Time
	ActiveConnections string
	RXSignal0         string
	RXSignal1         string
	RXSignal2         string
	RXSignal3         string
}

// CollectorConfig contains configuration for the metrics collector
type CollectorConfig struct {
	InfluxURL    string
	InfluxToken  string
	InfluxOrg    string
	InfluxBucket string
	TimeRange    string
}

// Collector manages metrics collection from InfluxDB
type Collector struct {
	config *CollectorConfig
	logger *logrus.Logger
}

// CSVRow represents a generic CSV row from InfluxDB
type CSVRow struct {
	Result       string
	Table        string
	Start        string
	Stop         string
	Time         string
	Value        string
	Field        string
	Measurement  string
	DeviceID     string
	ConnectionID string
	RadioID      string
	Source       string
}

// NewCollector creates a new metrics collector
func NewCollector(config *CollectorConfig, logger *logrus.Logger) *Collector {
	return &Collector{
		config: config,
		logger: logger,
	}
}

// queryInflux executes a Flux query against InfluxDB
func (c *Collector) queryInflux(query string) ([]byte, error) {
	url := fmt.Sprintf("%s/api/v2/query?org=%s", c.config.InfluxURL, c.config.InfluxOrg)
	req, err := http.NewRequest("POST", url, strings.NewReader(query))
	if err != nil {
		return nil, err
	}

	req.Header.Set("Authorization", "Token "+c.config.InfluxToken)
	req.Header.Set("Content-Type", "application/vnd.flux")
	req.Header.Set("Accept", "application/csv")

	client := &http.Client{Timeout: 30 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	return io.ReadAll(resp.Body)
}

// parseCSVResponse parses InfluxDB CSV response
func (c *Collector) parseCSVResponse(data []byte) ([]CSVRow, error) {
	reader := csv.NewReader(strings.NewReader(string(data)))
	var rows []CSVRow

	// Skip header and annotations
	lineNum := 0
	for {
		record, err := reader.Read()
		if err == io.EOF {
			break
		}
		if err != nil {
			return nil, err
		}

		lineNum++
		// Skip comment lines and header
		if len(record) == 0 || strings.HasPrefix(record[0], "#") ||
			(len(record) > 1 && record[1] == "result") {
			continue
		}

		// Parse data rows
		if len(record) >= 8 {
			row := CSVRow{
				Result:      getField(record, 1),
				Table:       getField(record, 2),
				Start:       getField(record, 3),
				Stop:        getField(record, 4),
				Time:        getField(record, 5),
				Value:       getField(record, 6),
				Field:       getField(record, 7),
				Measurement: getField(record, 8),
			}

			// Additional fields depending on query - check by field name patterns
			for i := 9; i < len(record); i++ {
				fieldValue := getField(record, i)
				// Try to identify fields by position and pattern
				if i == 9 {
					// Could be device_id, radio_frequency, or other tag
					if strings.HasPrefix(fieldValue, "S") {
						row.DeviceID = fieldValue
					}
				}
				if i == 10 {
					// Could be connection_id, radio_id, or other tag
					// radio_id is typically a single digit
					if len(fieldValue) <= 2 && fieldValue != "" {
						row.RadioID = fieldValue
					} else {
						row.ConnectionID = fieldValue
					}
				}
				if i == 11 {
					// Could be radio_id or source
					if strings.Contains(fieldValue, ":") || strings.Contains(fieldValue, ".") {
						row.Source = fieldValue
					} else if len(fieldValue) <= 2 {
						row.RadioID = fieldValue
					}
				}
			}

			// Source is typically the last field with : or .
			if row.Source == "" {
				lastField := getField(record, len(record)-1)
				if strings.Contains(lastField, ":") || strings.Contains(lastField, ".") {
					row.Source = lastField
				}
			}

			rows = append(rows, row)
		}
	}

	return rows, nil
}

func getField(record []string, index int) string {
	if index < len(record) {
		return strings.TrimSpace(record[index])
	}
	return ""
}

// CollectRNDevices collects all RN device metrics
func (c *Collector) CollectRNDevices() (map[string]*RNDevice, error) {
	devices := make(map[string]*RNDevice)

	// Query hostname for RN devices
	c.logger.Info("Querying RN hostnames...")
	hostnameQuery := fmt.Sprintf(`from(bucket: "%s")
  |> range(start: %s)
  |> filter(fn: (r) => r._field == "/connections/connection/system/state/hostname")
  |> group(columns: ["_measurement", "source", "connection_device-id"])
  |> last()`, c.config.InfluxBucket, c.config.TimeRange)

	data, err := c.queryInflux(hostnameQuery)
	if err != nil {
		return nil, err
	}

	rows, err := c.parseCSVResponse(data)
	if err != nil {
		return nil, err
	}

	for _, row := range rows {
		key := fmt.Sprintf("%s|%s|%s", row.Measurement, row.Source, row.DeviceID)
		if devices[key] == nil {
			devices[key] = &RNDevice{}
		}
		devices[key].Hostname = row.Value
		devices[key].Source = row.Source
		devices[key].DeviceID = row.DeviceID
		devices[key].Measurement = row.Measurement
		devices[key].Timestamp = formatTime(row.Time)
	}

	// Query DL-SNR
	c.logger.Info("Querying RN DL-SNR...")
	dlsnrQuery := fmt.Sprintf(`from(bucket: "%s")
  |> range(start: %s)
  |> filter(fn: (r) => r._field == "/connections/connection/state/dl-snr")
  |> group(columns: ["_measurement", "source", "connection_device-id"])
  |> last()`, c.config.InfluxBucket, c.config.TimeRange)

	data, err = c.queryInflux(dlsnrQuery)
	if err == nil {
		rows, _ = c.parseCSVResponse(data)
		for _, row := range rows {
			key := fmt.Sprintf("%s|%s|%s", row.Measurement, row.Source, row.DeviceID)
			// Only add metrics to devices that already exist (have hostname)
			if devices[key] != nil {
				devices[key].DLSNR = row.Value
			}
		}
	}

	// Query UL-SNR
	c.logger.Info("Querying RN UL-SNR...")
	ulsnrQuery := fmt.Sprintf(`from(bucket: "%s")
  |> range(start: %s)
  |> filter(fn: (r) => r._field == "/connections/connection/state/ul-snr")
  |> group(columns: ["_measurement", "source", "connection_device-id"])
  |> last()`, c.config.InfluxBucket, c.config.TimeRange)

	data, err = c.queryInflux(ulsnrQuery)
	if err == nil {
		rows, _ = c.parseCSVResponse(data)
		for _, row := range rows {
			key := fmt.Sprintf("%s|%s|%s", row.Measurement, row.Source, row.DeviceID)
			if devices[key] != nil {
				devices[key].ULSNR = row.Value
			}
		}
	}

	// Query Path Loss
	c.logger.Info("Querying RN Path Loss...")
	pathLossQuery := fmt.Sprintf(`from(bucket: "%s")
  |> range(start: %s)
  |> filter(fn: (r) => r._field == "/connections/connection/state/path-loss")
  |> group(columns: ["_measurement", "source", "connection_device-id"])
  |> last()`, c.config.InfluxBucket, c.config.TimeRange)

	data, err = c.queryInflux(pathLossQuery)
	if err == nil {
		rows, _ = c.parseCSVResponse(data)
		for _, row := range rows {
			key := fmt.Sprintf("%s|%s|%s", row.Measurement, row.Source, row.DeviceID)
			if devices[key] != nil {
				devices[key].PathLoss = row.Value
			}
		}
	}

	// Query RF Range
	c.logger.Info("Querying RN RF Range...")
	rfRangeQuery := fmt.Sprintf(`from(bucket: "%s")
  |> range(start: %s)
  |> filter(fn: (r) => r._field == "/connections/connection/state/rf-range")
  |> group(columns: ["_measurement", "source", "connection_device-id"])
  |> last()`, c.config.InfluxBucket, c.config.TimeRange)

	data, err = c.queryInflux(rfRangeQuery)
	if err == nil {
		rows, _ = c.parseCSVResponse(data)
		for _, row := range rows {
			key := fmt.Sprintf("%s|%s|%s", row.Measurement, row.Source, row.DeviceID)
			if devices[key] != nil {
				devices[key].RFRange = row.Value
			}
		}
	}

	// Query RX Signal Levels
	c.logger.Info("Querying RN RX Signal Levels...")
	rxSignalQuery := fmt.Sprintf(`from(bucket: "%s")
  |> range(start: %s)
  |> filter(fn: (r) => r._field == "/connections/connection/radios/radio/state/rx-signal-level/avg")
  |> group(columns: ["_measurement", "source", "connection_device-id", "radio_id"])
  |> last()`, c.config.InfluxBucket, c.config.TimeRange)

	data, err = c.queryInflux(rxSignalQuery)
	if err == nil {
		rows, _ = c.parseCSVResponse(data)
		for _, row := range rows {
			key := fmt.Sprintf("%s|%s|%s", row.Measurement, row.Source, row.DeviceID)
			if devices[key] != nil {
				switch row.RadioID {
				case "0":
					devices[key].RXSignal0 = row.Value
				case "1":
					devices[key].RXSignal1 = row.Value
				case "2":
					devices[key].RXSignal2 = row.Value
				case "3":
					devices[key].RXSignal3 = row.Value
				}
			}
		}
	}

	// Count devices with hostnames
	hostnameCount := 0
	for _, device := range devices {
		if device.Hostname != "" {
			hostnameCount++
		}
	}
	c.logger.Infof("Found %d RN devices with hostnames", hostnameCount)

	return devices, nil
}

// CollectBNDevices collects all BN device metrics
func (c *Collector) CollectBNDevices() (map[string]*BNDevice, error) {
	devices := make(map[string]*BNDevice)

	// Query hostname for BN devices
	c.logger.Info("Querying BN hostnames...")
	hostnameQuery := fmt.Sprintf(`from(bucket: "%s")
  |> range(start: %s)
  |> filter(fn: (r) => r._field == "/system/state/hostname")
  |> group(columns: ["_measurement", "source"])
  |> last()`, c.config.InfluxBucket, c.config.TimeRange)

	data, err := c.queryInflux(hostnameQuery)
	if err != nil {
		return nil, err
	}

	rows, err := c.parseCSVResponse(data)
	if err != nil {
		return nil, err
	}

	for _, row := range rows {
		key := fmt.Sprintf("%s|%s", row.Measurement, row.Source)
		if devices[key] == nil {
			devices[key] = &BNDevice{}
		}
		devices[key].Hostname = row.Value
		devices[key].Source = row.Source
		devices[key].Measurement = row.Measurement
		devices[key].Timestamp = formatTime(row.Time)
	}

	// Query Active Connections
	c.logger.Info("Querying BN Active Connections...")
	activeConnQuery := fmt.Sprintf(`from(bucket: "%s")
  |> range(start: %s)
  |> filter(fn: (r) => r._field == "/connections/global/state/active-connections")
  |> group(columns: ["_measurement", "source"])
  |> last()`, c.config.InfluxBucket, c.config.TimeRange)

	data, err = c.queryInflux(activeConnQuery)
	if err == nil {
		rows, _ = c.parseCSVResponse(data)
		for _, row := range rows {
			key := fmt.Sprintf("%s|%s", row.Measurement, row.Source)
			// Only add metrics to devices that already exist (have hostname)
			if devices[key] != nil {
				devices[key].ActiveConnections = row.Value
			}
		}
	}

	// Query RX Signal Levels for BN devices
	c.logger.Info("Querying BN RX Signal Levels...")
	rxSignalQuery := fmt.Sprintf(`from(bucket: "%s")
  |> range(start: %s)
  |> filter(fn: (r) => r._field == "/radios/radio/state/rx-signal-level/avg")
  |> group(columns: ["_measurement", "source", "radio_id"])
  |> last()`, c.config.InfluxBucket, c.config.TimeRange)

	data, err = c.queryInflux(rxSignalQuery)
	if err == nil {
		rows, _ = c.parseCSVResponse(data)
		for _, row := range rows {
			key := fmt.Sprintf("%s|%s", row.Measurement, row.Source)
			if devices[key] != nil {
				switch row.RadioID {
				case "0":
					devices[key].RXSignal0 = row.Value
				case "1":
					devices[key].RXSignal1 = row.Value
				case "2":
					devices[key].RXSignal2 = row.Value
				case "3":
					devices[key].RXSignal3 = row.Value
				}
			}
		}
	}

	// Count devices with hostnames
	hostnameCount := 0
	for _, device := range devices {
		if device.Hostname != "" {
			hostnameCount++
		}
	}
	c.logger.Infof("Found %d BN devices with hostnames", hostnameCount)

	return devices, nil
}

// // parseFloat safely converts string to float64
// func parseFloat(s string) float64 {
// 	var f float64
// 	fmt.Sscanf(s, "%f", &f)
// 	return f
// }

// // parseInt safely converts string to int
// func parseInt(s string) int {
// 	var i int
// 	fmt.Sscanf(s, "%d", &i)
// 	return i
// }

// formatTime parses ISO timestamp to time.Time
func formatTime(isoTime string) time.Time {
	t, err := time.Parse(time.RFC3339Nano, isoTime)
	if err != nil {
		// Try RFC3339 format
		t, _ = time.Parse(time.RFC3339, isoTime)
	}
	return t
}
