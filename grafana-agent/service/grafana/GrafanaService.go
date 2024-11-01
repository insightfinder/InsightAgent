package grafana

import (
	"context"
	"github.com/carlmjohnson/requests"
	requestModel "grafana-agent/service/grafana/models/request"
	"log"
	"strconv"
	"time"
)
import responseModel "grafana-agent/service/grafana/models/response"

const QUERY_API = "/api/ds/query"

type GrafanaService struct {
	Url           string
	ApiToken      string
	Username      string
	Password      string
	DatasourceUID string
	QueryDelay    time.Duration
}

func CreateGrafanaService(url string, apiToken string, username string, password string, datasourceUID string, queryDelay time.Duration) *GrafanaService {
	return &GrafanaService{
		Url:           url,
		ApiToken:      "Bearer " + apiToken,
		Username:      username,
		Password:      password,
		DatasourceUID: datasourceUID,
		QueryDelay:    queryDelay,
	}
}

func (grafanaService *GrafanaService) QueryData(queryExpression string, startTime time.Time, endTime time.Time, samplingInterval time.Duration) *responseModel.QueryResponseModel {
	queryResponse := responseModel.QueryResponseModel{}

	// Adjust the start and end time to account for the query delay
	startTime.Add(-grafanaService.QueryDelay)
	endTime.Add(-grafanaService.QueryDelay)

	startTimeStr := strconv.FormatInt(startTime.UnixMilli(), 10)
	endTimeStr := strconv.FormatInt(endTime.UnixMilli(), 10)

	// Parse samplingInterval to ms
	samplingIntervalMs := samplingInterval.Milliseconds()

	payload := requestModel.QueryRequestPayload{
		From: startTimeStr,
		To:   endTimeStr,
		Queries: []requestModel.QueryBody{
			{
				RefId: "A",
				Expr:  queryExpression,
				Range: true,
				DataSource: requestModel.QueryDataSource{
					UID: grafanaService.DatasourceUID,
				},
				IntervalMs:    int(samplingIntervalMs),
				MaxDataPoints: 1000000,
			},
		},
		Debug: false,
	}

	request := requests.
		URL(grafanaService.Url+QUERY_API).
		Method("POST").
		Header("Content-Type", "application/json").
		Header("Accept", "application/json").
		Header("Authorization", grafanaService.ApiToken).
		BodyJSON(&payload).
		ToJSON(&queryResponse)

	// Add Authorization header
	if grafanaService.ApiToken != "Bearer " {
		request.Header("Authorization", grafanaService.ApiToken)
	}
	if grafanaService.Username != "" && grafanaService.Password != "" {
		request.BasicAuth(grafanaService.Username, grafanaService.Password)
	}

	err := request.Fetch(context.Background())

	if err != nil {
		log.Fatalf("Error making request: %v", err)
	}

	return &queryResponse

}
