package edgecore

// GraphQL query structure
type GraphQLQuery struct {
	OperationName string                 `json:"operationName"`
	Variables     map[string]interface{} `json:"variables"`
	Query         string                 `json:"query"`
}

// GraphQL response error
type GraphQLError struct {
	Message string        `json:"message"`
	Path    []interface{} `json:"path"`
}

// Zone (Customer) structures
type Zone struct {
	ID                    string      `json:"id"`
	Email                 string      `json:"email"`
	Name                  string      `json:"name"`
	AccountIdentifier     *string     `json:"accountIdentifier"`
	LastModifiedTimestamp string      `json:"lastModifiedTimestamp"`
	Details               interface{} `json:"details"`
	Typename              string      `json:"__typename"`
}

type ZoneResponse struct {
	Data struct {
		GetCustomersForServiceProvider []Zone `json:"getCustomersForServiceProvider"`
	} `json:"data"`
	Errors []GraphQLError `json:"errors"`
}

// Access Point structures
type AccessPoint struct {
	ID         string                `json:"id"`
	Attributes AccessPointAttributes `json:"attributes"`
}

type AccessPointAttributes struct {
	CustomerID        string           `json:"customerId"`
	EquipmentID       string           `json:"equipmentId"`
	Name              string           `json:"name"`
	Radios            []string         `json:"radios"`
	ClientCount       *int             `json:"clientCount"`
	ClientCountMap    []map[string]int `json:"clientCountMap"`
	NoiseFloorDataMap []map[string]int `json:"noiseFloorDataMap"`
	ReportedIPAddr    string           `json:"reportedIpAddr"`
	EquipmentType     string           `json:"equipmentType"`
}

type AccessPointResponse struct {
	Data struct {
		FilterAccessPoints struct {
			Data []AccessPoint `json:"data"`
		} `json:"filterAccessPoints"`
	} `json:"data"`
	Errors []GraphQLError `json:"errors"`
}

// Equipment details structures
type EquipmentDetails struct {
	ID     string `json:"id"`
	Status struct {
		LatestApMetric struct {
			DetailsJSON *map[string]interface{} `json:"detailsJSON"`
		} `json:"latestApMetric"`
	} `json:"status"`
}

type EquipmentResponse struct {
	Data struct {
		GetEquipment EquipmentDetails `json:"getEquipment"`
	} `json:"data"`
	Errors []GraphQLError `json:"errors"`
}

// Metric data structure for InsightFinder
type MetricData struct {
	InstanceName  string  `json:"instanceName"`
	ComponentName string  `json:"componentName"`
	MetricName    string  `json:"metricName"`
	MetricValue   float64 `json:"metricValue"`
	Timestamp     int64   `json:"timestamp"`
	Zone          string  `json:"zone"`
	IPAddress     string  `json:"ipAddress"`
}

// Combined data structure for optimized queries
type CombinedAccessPointData struct {
	Zone             Zone              `json:"zone"`
	AccessPoint      AccessPoint       `json:"accessPoint"`
	EquipmentDetails *EquipmentDetails `json:"equipmentDetails"`
}

// Response structure for batch access point queries with aliases
type BatchAccessPointResponse struct {
	Data   map[string]interface{} `json:"data"`
	Errors []GraphQLError         `json:"errors"`
}

// Response structure for batch equipment details queries with aliases
type BatchEquipmentResponse struct {
	Data   map[string]interface{} `json:"data"`
	Errors []GraphQLError         `json:"errors"`
}

// Alarm structures for EdgeCore GraphQL API
type AlarmRequest struct {
	CustomerID   string `json:"customerId"`
	Limit        int    `json:"limit"`
	Acknowledged bool   `json:"acknowledged"`
}

type AlarmResponse struct {
	Data struct {
		FilterAlarms struct {
			Data []Alarm     `json:"data"`
			Meta interface{} `json:"meta"`
		} `json:"filterAlarms"`
	} `json:"data"`
	Errors []GraphQLError `json:"errors"`
}

type Alarm struct {
	ID         string          `json:"id"`
	Attributes AlarmAttributes `json:"attributes"`
}

type AlarmAttributes struct {
	CustomerID            string       `json:"customerId"`
	CustomerName          string       `json:"customerName"`
	Acknowledged          string       `json:"acknowledged"`
	AlarmCode             string       `json:"alarmCode"`
	CreatedTimestamp      string       `json:"createdTimestamp"`
	Details               AlarmDetails `json:"details"`
	EquipmentID           string       `json:"equipmentId"`
	LastModifiedTimestamp string       `json:"lastModifiedTimestamp"`
	LocationID            string       `json:"locationId"`
	OriginatorType        string       `json:"originatorType"`
	ScopeID               string       `json:"scopeId"`
	ScopeType             string       `json:"scopeType"`
	Severity              string       `json:"severity"`
	Equipment             Equipment    `json:"equipment"`
}

type AlarmDetails interface{}

type Equipment struct {
	Name          string          `json:"name"`
	ID            string          `json:"id"`
	EquipmentType string          `json:"equipmentType"`
	Location      Location        `json:"location"`
	Status        EquipmentStatus `json:"status"`
}

type Location struct {
	Name string `json:"name"`
}

type EquipmentStatus struct {
	Protocol Protocol `json:"protocol"`
}

type Protocol struct {
	Details StatusDetails `json:"details"`
}

type StatusDetails struct {
	ReportedIPV4Addr string `json:"reportedIpV4Addr"`
}
