package insightfinder

import (
	"context"
	"encoding/json"
	"fmt"
	"github.com/carlmjohnson/requests"
	ifrequest "grafana-agent/service/insightfinder/models/request"
	"log/slog"
)

func (ifclient *InsightFinder) SendMetricData(data *ifrequest.MetricDataReceivePayload) {

	curTotal := 0
	var newPayload = ifrequest.MetricDataReceivePayload{
		ProjectName:     data.ProjectName,
		UserName:        data.UserName,
		InstanceDataMap: make(map[string]ifrequest.InstanceData),
		SystemName:      ifclient.SystemName,
	}
	for instanceName, istData := range data.InstanceDataMap {
		instanceData, ok := newPayload.InstanceDataMap[instanceName]
		if !ok {
			// Current NodeInstance didn't exist
			instanceData = ifrequest.InstanceData{
				InstanceName:       istData.InstanceName,
				ComponentName:      istData.ComponentName,
				DataInTimestampMap: make(map[int64]ifrequest.DataInTimestamp),
			}
			newPayload.InstanceDataMap[instanceName] = instanceData
		}
		for timeStamp, tsData := range istData.DataInTimestampMap {
			// Need to send out the data in the same timestamp in one payload
			dataBytes, err := json.Marshal(tsData)
			if err != nil {
				panic("[ERORR] There's issue form json data for DataInTimestampMap.")
			}
			// Add the data into the payload
			instanceData.DataInTimestampMap[timeStamp] = tsData
			// The json.Marshal transform the data into bytes so the length will be the actual size.
			curTotal += len(dataBytes)
			if curTotal > CHUNK_SIZE {
				request := ifrequest.IFMetricPostRequestPayload{
					LicenseKey: ifclient.LicenseKey,
					UserName:   ifclient.Username,
					Data:       *data,
				}
				jData, err := json.Marshal(request)
				if err != nil {
					panic(err)
				}
				ifclient.SendMetricByteData(jData)
				curTotal = 0
				newPayload = ifrequest.MetricDataReceivePayload{
					ProjectName:     data.ProjectName,
					UserName:        data.UserName,
					InstanceDataMap: make(map[string]ifrequest.InstanceData),
					SystemName:      ifclient.SystemName,
				}
				newPayload.InstanceDataMap[instanceName] = ifrequest.InstanceData{
					InstanceName:       istData.InstanceName,
					ComponentName:      istData.InstanceName,
					DataInTimestampMap: make(map[int64]ifrequest.DataInTimestamp),
				}
			}
		}
	}
	request := ifrequest.IFMetricPostRequestPayload{
		LicenseKey: ifclient.LicenseKey,
		UserName:   ifclient.Username,
		Data:       *data,
	}
	jData, err := json.Marshal(request)
	if err != nil {
		panic(err)
	}
	ifclient.SendMetricByteData(jData)
}

func (ifclient *InsightFinder) SendMetricByteData(data []byte) {
	slog.Info("-------- Sending data to InsightFinder --------")

	if len(data) > MAX_PACKET_SIZE {
		panic("[ERROR]The packet size is too large.")
	}
	var response string
	slog.Info("Prepare to send out " + fmt.Sprint(len(data)) + " bytes data to IF")
	err := requests.URL(ifclient.Endpoint).
		Path(METRIC_DATA_API).
		Header("Content-Type", "application/json").
		BodyBytes(data).Post().
		ToString(&response).
		Fetch(context.Background())
	if err != nil {
		slog.Error(string(response))
	}
	//response, _ = SendRequest(
	//	http.MethodPost,
	//	endpoint,
	//	bytes.NewBuffer(data),
	//	headers,
	//	AuthRequest{},
	//)
	//var result map[string]interface{}
	//json.Unmarshal(response, &result)

}
