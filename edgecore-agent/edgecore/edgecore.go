package edgecore

import (
	"bytes"
	"crypto/tls"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strconv"
	"strings"
	"sync"
	"time"

	config "github.com/insightfinder/edgecore-agent/configs"
	"github.com/sirupsen/logrus"
)

type Service struct {
	config               config.EdgeCoreConfig
	client               *http.Client
	authService          *AuthService
	LastSentAlarmCreated time.Time
	SessionMutex         sync.RWMutex
}

// NewService creates a new EdgeCore service
func NewService(cfg config.EdgeCoreConfig) *Service {
	// Configure HTTP client
	transport := &http.Transport{}
	if !cfg.VerifySSL {
		transport.TLSClientConfig = &tls.Config{InsecureSkipVerify: true}
	}

	client := &http.Client{
		Transport: transport,
		Timeout:   30 * time.Second,
	}

	return &Service{
		config:      cfg,
		client:      client,
		authService: NewAuthService(cfg),
	}
}

// cleanRadioName converts radio frequency identifiers to cleaner format
// e.g., is5GHz -> 5GHz, is2dot4GHz -> 2.4GHz, is6GHz -> 6GHz
func cleanRadioName(radio string) string {
	switch radio {
	case "is5GHz":
		return "5GHz"
	case "is2dot4GHz":
		return "2.4GHz"
	case "is6GHz":
		return "6GHz"
	case "is5GHzU":
		return "5GHzU"
	case "is2dot4GHzU":
		return "2.4GHzU"
	case "is6GHzU":
		return "6GHzU"
	case "is5GHzL":
		return "5GHzL"
	case "is2dot4GHzL":
		return "2.4GHzL"
	case "is6GHzL":
		return "6GHzL"
	default:
		return radio // Return as-is if no match
	}
}

// HealthCheck tests connection to the EdgeCore GraphQL API
func (s *Service) HealthCheck() error {
	// Simple GraphQL introspection query to test connectivity
	introspectionQuery := `{"query": "{ __schema { types { name } } }"}`

	req, err := http.NewRequest("POST", s.config.BaseURL, bytes.NewBufferString(introspectionQuery))
	if err != nil {
		return fmt.Errorf("failed to create health check request: %v", err)
	}

	req.Header.Set("Content-Type", "application/json")

	resp, err := s.client.Do(req)
	if err != nil {
		return fmt.Errorf("health check request failed: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("health check failed with status: %d", resp.StatusCode)
	}

	return nil
}

// makeAuthenticatedRequest creates an authenticated GraphQL request
func (s *Service) makeAuthenticatedRequest(query interface{}) (*http.Response, error) {
	// Ensure we have a valid token
	if err := s.authService.EnsureValidToken(); err != nil {
		return nil, fmt.Errorf("authentication failed: %v", err)
	}

	jsonBody, err := json.Marshal(query)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal query: %v", err)
	}

	req, err := http.NewRequest("POST", s.config.BaseURL, bytes.NewBuffer(jsonBody))
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %v", err)
	}

	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", fmt.Sprintf("Bearer %s", s.authService.GetAccessToken()))

	return s.client.Do(req)
}

// GetCustomersForServiceProvider fetches zones (customers) for the service provider
func (s *Service) GetCustomersForServiceProvider() ([]Zone, error) {
	query := GraphQLQuery{
		OperationName: "getCustomersForServiceProvider",
		Variables: map[string]interface{}{
			"serviceProviderId": s.config.ServiceProviderID,
		},
		Query: `query getCustomersForServiceProvider($serviceProviderId: ID!, $name: String, $operationalState: String) {
			getCustomersForServiceProvider(
				serviceProviderId: $serviceProviderId
				name: $name
				operationalState: $operationalState
			) {
				id
				email
				name
				accountIdentifier
				lastModifiedTimestamp
				details
				__typename
			}
		}`,
	}

	resp, err := s.makeAuthenticatedRequest(query)
	if err != nil {
		return nil, fmt.Errorf("failed to make request: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("request failed with status %d: %s", resp.StatusCode, string(body))
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("failed to read response: %v", err)
	}

	var response ZoneResponse
	if err := json.Unmarshal(body, &response); err != nil {
		return nil, fmt.Errorf("failed to parse response: %v", err)
	}

	if len(response.Errors) > 0 {
		return nil, fmt.Errorf("GraphQL errors: %v", response.Errors)
	}

	return response.Data.GetCustomersForServiceProvider, nil
}

// GetAllMetrics fetches all metrics for provided zones and their access points using optimized queries
func (s *Service) GetAllMetrics(zones []Zone) ([]MetricData, error) {
	logrus.Debug("Starting to collect all metrics using optimized queries with provided zones")

	var allMetrics []MetricData

	// Step 2: Get access points for all zones at once using aliases
	allAccessPoints, err := s.GetAllAccessPointsWithMetrics(zones)
	if err != nil {
		return nil, fmt.Errorf("failed to get access points with metrics: %v", err)
	}

	// Step 3: Convert to metrics format
	for _, apData := range allAccessPoints {
		metrics := s.convertToMetricsFromCombined(apData)
		allMetrics = append(allMetrics, metrics...)
	}

	logrus.Debugf("Collected %d metric data points from %d access points", len(allMetrics), len(allAccessPoints))
	return allMetrics, nil
}

// GetAllAccessPointsWithMetrics gets access points from all zones and their detailed metrics in optimized queries
func (s *Service) GetAllAccessPointsWithMetrics(zones []Zone) ([]CombinedAccessPointData, error) {
	logrus.Debug("Fetching access points and metrics for all zones using optimized queries")

	var allAccessPoints []CombinedAccessPointData

	// Process zones in batches to avoid hitting query limits
	batchSize := 40 // Adjust based on GraphQL server limits
	for i := 0; i < len(zones); i += batchSize {
		end := i + batchSize
		if end > len(zones) {
			end = len(zones)
		}

		zoneBatch := zones[i:end]
		batchData, err := s.getAccessPointsBatch(zoneBatch)
		if err != nil {
			logrus.Errorf("Failed to get access points batch: %v", err)
			continue
		}

		allAccessPoints = append(allAccessPoints, batchData...)
	}

	return allAccessPoints, nil
}

// getAccessPointsBatch gets access points and their metrics for a batch of zones using GraphQL aliases
func (s *Service) getAccessPointsBatch(zones []Zone) ([]CombinedAccessPointData, error) {
	// Build query with aliases for each zone
	var queryParts []string
	var variables = make(map[string]interface{})

	for i, zone := range zones {
		alias := fmt.Sprintf("zone_%d", i)
		queryParts = append(queryParts, fmt.Sprintf(`
			%s: filterAccessPoints(
				customerId: $customerId_%d
				equipmentType: "AP"
				ctx: {
					model_type: "EsPaginationContext"
					paginationType: "searchAfter"
					pitId: null
					lastUsed: 0
					offset: 0
					pageSize: 5000
				}
			) {
				data {
					id
					attributes {
						customerId
						equipmentId
						name
						radios
						clientCount
						clientCountMap
						noiseFloorDataMap
						reportedIpAddr
						equipmentType
					}
				}
			}`, alias, i))

		variables[fmt.Sprintf("customerId_%d", i)] = zone.ID
	}

	query := GraphQLQuery{
		OperationName: "GetAllAccessPointsBatch",
		Variables:     variables,
		Query: fmt.Sprintf(`query GetAllAccessPointsBatch(%s) {
			%s
		}`, s.buildVariableDeclarations(len(zones)), strings.Join(queryParts, "\n")),
	}

	resp, err := s.makeAuthenticatedRequest(query)
	if err != nil {
		return nil, fmt.Errorf("failed to make request: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("request failed with status %d: %s", resp.StatusCode, string(body))
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("failed to read response: %v", err)
	}

	var response BatchAccessPointResponse
	if err := json.Unmarshal(body, &response); err != nil {
		return nil, fmt.Errorf("failed to parse response: %v", err)
	}

	if len(response.Errors) > 0 {
		return nil, fmt.Errorf("GraphQL errors: %v", response.Errors)
	}

	// Step 1: Extract all access points from all zones first
	var allAccessPoints []CombinedAccessPointData
	var allAPsData []struct {
		zone Zone
		ap   AccessPoint
	}

	for i, zone := range zones {
		alias := fmt.Sprintf("zone_%d", i)
		if zoneData, exists := response.Data[alias]; exists {
			if accessPointData, ok := zoneData.(map[string]interface{}); ok {
				if dataArray, ok := accessPointData["data"].([]interface{}); ok {
					for _, apInterface := range dataArray {
						if apBytes, err := json.Marshal(apInterface); err == nil {
							var ap AccessPoint
							if err := json.Unmarshal(apBytes, &ap); err == nil {
								allAPsData = append(allAPsData, struct {
									zone Zone
									ap   AccessPoint
								}{zone: zone, ap: ap})
							}
						}
					}
				}
			}
		}
	}

	// Step 2: Get ALL equipment details in ONE massive batch query for ultra performance
	var allAPIDs []string
	for _, apData := range allAPsData {
		allAPIDs = append(allAPIDs, apData.ap.ID)
	}

	var detailsMap map[string]*EquipmentDetails
	if len(allAPIDs) > 0 {
		var err error
		detailsMap, err = s.getEquipmentDetailsMassiveBatch(allAPIDs)
		if err != nil {
			logrus.Errorf("Failed to get equipment details in batch: %v", err)
			detailsMap = make(map[string]*EquipmentDetails) // Continue with empty details
		}
	}

	// Step 3: Combine all data
	for _, apData := range allAPsData {
		details := detailsMap[apData.ap.ID]
		allAccessPoints = append(allAccessPoints, CombinedAccessPointData{
			Zone:             apData.zone,
			AccessPoint:      apData.ap,
			EquipmentDetails: details,
		})
	}

	return allAccessPoints, nil
}

// convertToMetrics converts EdgeCore data to metric format
func (s *Service) convertToMetrics(zone Zone, ap AccessPoint, details *EquipmentDetails) []MetricData {
	var metrics []MetricData
	timestamp := time.Now().Unix() * 1000 // milliseconds

	// Extract basic metrics from AP attributes
	if ap.Attributes.ClientCount != nil {
		metrics = append(metrics, MetricData{
			InstanceName:  ap.Attributes.Name,
			ComponentName: ap.Attributes.EquipmentType,
			MetricName:    "ClientCount Total",
			MetricValue:   float64(*ap.Attributes.ClientCount),
			Timestamp:     timestamp,
			Zone:          zone.Name,
			IPAddress:     ap.Attributes.ReportedIPAddr,
		})
	}

	// Extract radio-specific metrics from AP attributes
	if len(ap.Attributes.ClientCountMap) > 0 {
		for radio, count := range ap.Attributes.ClientCountMap[0] {
			metrics = append(metrics, MetricData{
				InstanceName:  ap.Attributes.Name,
				ComponentName: ap.Attributes.EquipmentType,
				MetricName:    fmt.Sprintf("ClientCount %s", cleanRadioName(radio)),
				MetricValue:   float64(count),
				Timestamp:     timestamp,
				Zone:          zone.Name,
				IPAddress:     ap.Attributes.ReportedIPAddr,
			})
		}
	}

	if len(ap.Attributes.NoiseFloorDataMap) > 0 {
		for radio, noiseFloor := range ap.Attributes.NoiseFloorDataMap[0] {
			metrics = append(metrics, MetricData{
				InstanceName:  ap.Attributes.Name,
				ComponentName: ap.Attributes.EquipmentType,
				MetricName:    fmt.Sprintf("NoiseFloor %s", cleanRadioName(radio)),
				MetricValue:   float64(noiseFloor),
				Timestamp:     timestamp,
				Zone:          zone.Name,
				IPAddress:     ap.Attributes.ReportedIPAddr,
			})
		}
	}

	// Extract detailed metrics from equipment details
	if details != nil && details.Status.LatestApMetric.DetailsJSON != nil {
		detailsJSON := *details.Status.LatestApMetric.DetailsJSON

		// Channel utilization per radio
		if channelUtil, ok := detailsJSON["channelUtilizationPerRadio"].(map[string]interface{}); ok {
			for radio, util := range channelUtil {
				if utilValue, ok := util.(float64); ok {
					metrics = append(metrics, MetricData{
						InstanceName:  ap.Attributes.Name,
						ComponentName: ap.Attributes.EquipmentType,
						MetricName:    fmt.Sprintf("ChannelUtilization %s", cleanRadioName(radio)),
						MetricValue:   utilValue,
						Timestamp:     timestamp,
						Zone:          zone.Name,
						IPAddress:     ap.Attributes.ReportedIPAddr,
					})
				}
			}
		}

		// Radio statistics (RSSI)
		if radioStats, ok := detailsJSON["radioStatsPerRadio"].(map[string]interface{}); ok {
			for radio, stats := range radioStats {
				if statsMap, ok := stats.(map[string]interface{}); ok {
					if rssi, ok := statsMap["rxLastRssi"].(float64); ok {
						metrics = append(metrics, MetricData{
							InstanceName:  ap.Attributes.Name,
							ComponentName: ap.Attributes.EquipmentType,
							MetricName:    fmt.Sprintf("RSSI %s", cleanRadioName(radio)),
							MetricValue:   rssi,
							Timestamp:     timestamp,
							Zone:          zone.Name,
							IPAddress:     ap.Attributes.ReportedIPAddr,
						})
					}
				}
			}
		}

	}

	return metrics
}

// convertToMetricsFromCombined converts combined access point data to metrics
func (s *Service) convertToMetricsFromCombined(apData CombinedAccessPointData) []MetricData {
	return s.convertToMetrics(apData.Zone, apData.AccessPoint, apData.EquipmentDetails)
}

// buildVariableDeclarations builds GraphQL variable declarations for batch queries
func (s *Service) buildVariableDeclarations(count int) string {
	var declarations []string
	for i := 0; i < count; i++ {
		declarations = append(declarations, fmt.Sprintf("$customerId_%d: ID", i))
	}
	return strings.Join(declarations, ", ")
}

// getEquipmentDetailsMassiveBatch gets equipment details for ALL access points in ONE query using aliases
// This is the ultimate optimization - single API call for all detailed metrics
func (s *Service) getEquipmentDetailsMassiveBatch(apIDs []string) (map[string]*EquipmentDetails, error) {
	if len(apIDs) == 0 {
		return map[string]*EquipmentDetails{}, nil
	}

	// Build one massive query with aliases for ALL access points
	var queryBuilder strings.Builder
	queryBuilder.WriteString("query GetAllEquipmentDetails {")

	for i, apID := range apIDs {
		alias := fmt.Sprintf("eq_%d", i)
		queryBuilder.WriteString(fmt.Sprintf(`
			%s: getEquipment(id: "%s") {
				id
				status {
					latestApMetric {
						detailsJSON
					}
				}
			}`, alias, apID))
	}
	queryBuilder.WriteString("}")

	query := map[string]interface{}{
		"query": queryBuilder.String(),
	}

	resp, err := s.makeAuthenticatedRequest(query)
	if err != nil {
		return nil, fmt.Errorf("failed to make massive batch request: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("massive batch GraphQL request failed with status %d: %s", resp.StatusCode, string(body))
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("failed to read massive batch response: %v", err)
	}

	var response struct {
		Data   map[string]interface{} `json:"data"`
		Errors []GraphQLError         `json:"errors"`
	}

	if err := json.Unmarshal(body, &response); err != nil {
		return nil, fmt.Errorf("failed to unmarshal massive batch response: %v", err)
	}

	if len(response.Errors) > 0 {
		return nil, fmt.Errorf("massive batch GraphQL errors: %v", response.Errors)
	}

	// Parse all aliased responses
	detailsMap := make(map[string]*EquipmentDetails)
	for i, apID := range apIDs {
		alias := fmt.Sprintf("eq_%d", i)
		if aliasData, exists := response.Data[alias]; exists && aliasData != nil {
			if equipmentBytes, err := json.Marshal(aliasData); err == nil {
				var equipment EquipmentDetails
				if err := json.Unmarshal(equipmentBytes, &equipment); err == nil {
					detailsMap[apID] = &equipment
				}
			}
		}
	}

	logrus.Infof("Successfully retrieved detailed metrics for %d/%d access points in single query", len(detailsMap), len(apIDs))
	return detailsMap, nil
}

// GetAlarms fetches alarms/logs from EdgeCore GraphQL API for provided zones using massive batch query
func (s *Service) GetAlarms(zones []Zone) ([]Alarm, error) {
	logrus.Debug("Starting alarm collection for provided zones using massive batch query")

	// Get all alarms from all zones in ONE massive batch query
	allAlarms, err := s.getAlarmsMassiveBatch(zones)
	if err != nil {
		logrus.Errorf("Failed to get alarms in massive batch: %v", err)
		return nil, err
	}

	// Filter: only alarms created in the last minute and not yet sent
	now := time.Now().UTC()
	cutoff := now.Add(-1 * time.Minute)

	var filtered []Alarm
	var maxCreated time.Time

	parseTimestamp := func(ts string) time.Time {
		// Convert millisecond timestamp string to time
		if tsInt, err := strconv.ParseInt(ts, 10, 64); err == nil {
			return time.Unix(0, tsInt*1e6).UTC() // Convert milliseconds to nanoseconds
		}
		return time.Time{}
	}

	s.SessionMutex.Lock()
	lastSent := s.LastSentAlarmCreated
	s.SessionMutex.Unlock()

	for _, alarm := range allAlarms {
		createdTime := parseTimestamp(alarm.Attributes.CreatedTimestamp)

		// Only in last minute
		if createdTime.IsZero() || createdTime.Before(cutoff) {
			continue
		}
		// Only newer than what we've already sent
		if !lastSent.IsZero() && !createdTime.After(lastSent) {
			continue
		}

		filtered = append(filtered, alarm)
		if createdTime.After(maxCreated) {
			maxCreated = createdTime
		}
	}

	// Update the watermark so we don't resend
	if !maxCreated.IsZero() {
		s.SessionMutex.Lock()
		if maxCreated.After(s.LastSentAlarmCreated) {
			s.LastSentAlarmCreated = maxCreated
		}
		s.SessionMutex.Unlock()
	}

	logrus.Debugf("Retrieved %d total alarms, %d new in last minute (watermark=%s)",
		len(allAlarms), len(filtered), s.LastSentAlarmCreated.Format(time.RFC3339Nano))

	return filtered, nil
}

// getAlarmsMassiveBatch gets alarms for ALL zones in ONE query using aliases - ultimate optimization
func (s *Service) getAlarmsMassiveBatch(zones []Zone) ([]Alarm, error) {
	if len(zones) == 0 {
		return []Alarm{}, nil
	}

	// Build one massive query with aliases for ALL zones
	var queryBuilder strings.Builder
	var variables = make(map[string]interface{})

	queryBuilder.WriteString("query GetAllAlarmsForAllZones(")

	// Build variable declarations
	var varDeclarations []string
	for i := range zones {
		varDeclarations = append(varDeclarations, fmt.Sprintf("$customerId_%d: ID", i))
	}
	queryBuilder.WriteString(strings.Join(varDeclarations, ", "))
	queryBuilder.WriteString(") {")

	// Build aliased queries for each zone
	for i, zone := range zones {
		alias := fmt.Sprintf("zone_%d", i)
		variables[fmt.Sprintf("customerId_%d", i)] = zone.ID

		queryBuilder.WriteString(fmt.Sprintf(`
			%s: filterAlarms(
				customerId: $customerId_%d
				limit: 2000
				acknowledged: false
			) {
				data {
					id
					attributes {
						customerId
						acknowledged
						alarmCode
						createdTimestamp
						details
						equipmentId
						lastModifiedTimestamp
						locationId
						originatorType
						scopeId
						scopeType
						severity
						equipment {
							name
							id
							equipmentType
							location {
								name
								__typename
							}
							status {
								protocol {
									details {
										reportedIpV4Addr
										__typename
									}
									__typename
								}
								__typename
							}
							__typename
						}
						__typename
					}
					__typename
				}
				meta
				__typename
			}`, alias, i))
	}
	queryBuilder.WriteString("}")

	query := map[string]interface{}{
		"query":     queryBuilder.String(),
		"variables": variables,
	}

	resp, err := s.makeAuthenticatedRequest(query)
	if err != nil {
		return nil, fmt.Errorf("failed to make massive batch alarm request: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("massive batch alarm request failed with status %d: %s", resp.StatusCode, string(body))
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("failed to read massive batch alarm response: %v", err)
	}

	var response struct {
		Data   map[string]interface{} `json:"data"`
		Errors []GraphQLError         `json:"errors"`
	}

	if err := json.Unmarshal(body, &response); err != nil {
		return nil, fmt.Errorf("failed to unmarshal massive batch alarm response: %v", err)
	}

	if len(response.Errors) > 0 {
		return nil, fmt.Errorf("massive batch alarm GraphQL errors: %v", response.Errors)
	}

	// Parse all aliased alarm responses
	var allAlarms []Alarm
	for i, zone := range zones {
		alias := fmt.Sprintf("zone_%d", i)
		if aliasData, exists := response.Data[alias]; exists && aliasData != nil {
			if alarmDataBytes, err := json.Marshal(aliasData); err == nil {
				var alarmResponse struct {
					Data []Alarm     `json:"data"`
					Meta interface{} `json:"meta"`
				}
				if err := json.Unmarshal(alarmDataBytes, &alarmResponse); err == nil {
					allAlarms = append(allAlarms, alarmResponse.Data...)
					logrus.Debugf("Retrieved %d alarms for zone %s (%s)", len(alarmResponse.Data), zone.Name, zone.ID)
				} else {
					logrus.Errorf("Failed to parse alarms for zone %s (%s): %v", zone.Name, zone.ID, err)
				}
			}
		}
	}

	logrus.Infof("Successfully retrieved %d total alarms from %d zones", len(allAlarms), len(zones))
	return allAlarms, nil
}
