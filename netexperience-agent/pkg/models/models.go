package models

import "time"

// MetricData represents metric data for InsightFinder
type MetricData struct {
	Timestamp     int64                  `json:"timestamp"`
	InstanceName  string                 `json:"instanceName"`
	Data          map[string]interface{} `json:"data"`
	Zone          string                 `json:"zone,omitempty"`
	ComponentName string                 `json:"componentName,omitempty"`
	IP            string                 `json:"ip,omitempty"`
}

// Customer represents a NetExperience customer
type Customer struct {
	ID    int    `json:"id"`
	Name  string `json:"name"`
	Email string `json:"email"`
}

// Equipment represents network equipment (AP)
type Equipment struct {
	ID             int        `json:"id"`
	CustomerID     int        `json:"customerId"`
	ProfileID      int        `json:"profileId"`
	LocationID     int        `json:"locationId"`
	EquipmentType  string     `json:"equipmentType"`
	InventoryID    string     `json:"inventoryId"`
	Name           string     `json:"name"`
	BaseMacAddress MacAddress `json:"baseMacAddress"`
	IPAddress      string     `json:"ipAddress,omitempty"` // Fetched from status endpoint
}

// MacAddress represents a MAC address
type MacAddress struct {
	Address         string `json:"address"`
	AddressAsString string `json:"addressAsString"`
}

// PaginationContext for API pagination
type PaginationContext struct {
	Cursor                 string `json:"cursor"`
	LastPage               bool   `json:"lastPage"`
	LastReturnedPageNumber int    `json:"lastReturnedPageNumber"`
	MaxItemsPerPage        int    `json:"maxItemsPerPage"`
	TotalItemsReturned     int    `json:"totalItemsReturned"`
}

// PaginationResponse for paginated API responses
type PaginationResponse struct {
	Items   interface{}       `json:"items"`
	Context PaginationContext `json:"context"`
}

// ServiceMetric represents a service metric from the API
type ServiceMetric struct {
	CustomerID       int         `json:"customerId"`
	EquipmentID      int         `json:"equipmentId"`
	LocationID       int         `json:"locationId"`
	ClientMac        int64       `json:"clientMac"`
	DataType         string      `json:"dataType"`
	CreatedTimestamp int64       `json:"createdTimestamp"`
	Details          interface{} `json:"details"`
	ClientMacAddress *MacAddress `json:"clientMacAddress"`
}

// ApNodeMetrics represents AP node metrics
type ApNodeMetrics struct {
	InventoryID                string                  `json:"inventoryId"`
	PeriodLengthSec            int                     `json:"periodLengthSec"`
	ClientMacAddressesPerRadio map[string][]MacAddress `json:"clientMacAddressesPerRadio"`
	ChannelUtilizationPerRadio map[string]float64      `json:"channelUtilizationPerRadio"`
	DataType                   string                  `json:"dataType"`
	ClientCount                int                     `json:"clientCount,omitempty"`
	SourceTimestampMs          int64                   `json:"sourceTimestampMs"`
}

// ClientMetrics represents client metrics
type ClientMetrics struct {
	NumRxPackets           int     `json:"numRxPackets,omitempty"`
	NumTxPackets           int     `json:"numTxPackets,omitempty"`
	NumRxBytes             int     `json:"numRxBytes,omitempty"`
	NumTxBytes             int     `json:"numTxBytes,omitempty"`
	RSSI                   int     `json:"rssi,omitempty"`
	AverageTxRate          float64 `json:"averageTxRate,omitempty"`
	AverageRxRate          float64 `json:"averageRxRate,omitempty"`
	NumTxFramesTransmitted int     `json:"numTxFramesTransmitted,omitempty"`
	NumRxFramesReceived    int     `json:"numRxFramesReceived,omitempty"`
	RxBytes                int     `json:"rxBytes,omitempty"`
	NumTxDropped           int     `json:"numTxDropped,omitempty"`
	NumTxDataRetries       int     `json:"numTxDataRetries,omitempty"`
	PeriodLengthSec        int     `json:"periodLengthSec,omitempty"`
	DataType               string  `json:"dataType"`
	SourceTimestampMs      int64   `json:"sourceTimestampMs"`
}

// EquipmentMetrics holds aggregated metrics for an equipment
type EquipmentMetrics struct {
	EquipmentID   int
	EquipmentName string
	CustomerID    int
	CustomerName  string
	IPAddress     string
	Timestamp     time.Time

	// Client counts
	TotalClients int
	Clients5GHz  int
	Clients24GHz int

	// Channel utilization
	ChannelUtilization5GHz  float64
	ChannelUtilization24GHz float64

	// RSSI metrics
	AverageRSSI        float64
	ClientsRSSIBelow74 int
	ClientsRSSIBelow78 int
	ClientsRSSIBelow80 int

	// RSSI percentages (only calculated if total clients >= threshold)
	PercentRSSIBelow74 float64
	PercentRSSIBelow78 float64
	PercentRSSIBelow80 float64

	// WAN Port Speed
	WANPortSpeed int
}

// CachedData represents cached customer and equipment data
type CachedData struct {
	Customers            map[int]*Customer
	EquipmentByCustomer  map[int][]*Equipment
	LastCustomerRefresh  time.Time
	LastEquipmentRefresh time.Time
	LastIPRefresh        time.Time
}
