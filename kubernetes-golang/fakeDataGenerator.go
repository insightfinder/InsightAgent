package main

import (
	"encoding/json"
	"fmt"
	"math/rand"
)

type FakeMetricsData struct {
	CapacityLimitInKb                              int64
	CapacityInUseInKb                              int64
	UnreachableUnusedCapacityInKb                  int64
	SnapCapacityInUseOccupiedInKb                  int64
	RmPendingAllocatedInKb                         int64
	ChecksumCapacityInKbnumber                     int64
	SpareCapacityInKbnumber                        int64
	CapacityAvailableForVolumeAllocationInKbnumber int64
	VolumeAllocationLimitInKbnumber                int64
	ProtectedCapacityInKbnumber                    int64
	DegradedHealthyCapacityInKbnumber              int64
	DegradedFailedCapacityInKbnumber               int64
	FailedCapacityInKbnumber                       int64
	SemiProtectedCapacityInKbnumber                int64
	InMaintenanceCapacityInKbnumber                int64
	TempCapacityInKbnumber                         int64
	ProtectedVacInKbnumber                         int64
	DegradedHealthyVacInKbnumber                   int64
	DegradedFailedVacInKbnumber                    int64
	FailedVacInKbnumber                            int64
	SemiProtectedVacInKbnumber                     int64
	InMaintenanceVacInKbnumber                     int64
	TempCapacityVacInKbnumber                      int64
	MovingCapacityInKbnumber                       int64
	ActiveMovingCapacityInKbnumber                 int64
	PendingMovingCapacityInKbnumber                int64
	FwdRebuildCapacityInKbnumber                   int64
	ActiveFwdRebuildCapacityInKbnumber             int64
	PendingFwdRebuildCapacityInKb                  int64
	BckRebuildCapacityInKbnumber                   int64
	ActiveBckRebuildCapacityInKbnumber             int64
	PendingBckRebuildCapacityInKbnumber            int64
}

func GetFakeMetricData() []byte {
	data := FakeMetricsData{
		CapacityLimitInKb:                              rand.Int63n(1000),
		CapacityInUseInKb:                              rand.Int63n(1000),
		UnreachableUnusedCapacityInKb:                  rand.Int63n(1000),
		SnapCapacityInUseOccupiedInKb:                  rand.Int63n(1000),
		RmPendingAllocatedInKb:                         rand.Int63n(1000),
		ChecksumCapacityInKbnumber:                     rand.Int63n(1000),
		SpareCapacityInKbnumber:                        rand.Int63n(1000),
		CapacityAvailableForVolumeAllocationInKbnumber: rand.Int63n(1000),
		VolumeAllocationLimitInKbnumber:                rand.Int63n(1000),
		ProtectedCapacityInKbnumber:                    rand.Int63n(1000),
		DegradedHealthyCapacityInKbnumber:              rand.Int63n(1000),
		DegradedFailedCapacityInKbnumber:               rand.Int63n(1000),
		FailedCapacityInKbnumber:                       rand.Int63n(1000),
		SemiProtectedCapacityInKbnumber:                rand.Int63n(1000),
		InMaintenanceCapacityInKbnumber:                rand.Int63n(1000),
		TempCapacityInKbnumber:                         rand.Int63n(1000),
		ProtectedVacInKbnumber:                         rand.Int63n(1000),
		DegradedHealthyVacInKbnumber:                   rand.Int63n(1000),
		DegradedFailedVacInKbnumber:                    rand.Int63n(1000),
		FailedVacInKbnumber:                            rand.Int63n(1000),
		SemiProtectedVacInKbnumber:                     rand.Int63n(1000),
		InMaintenanceVacInKbnumber:                     rand.Int63n(1000),
		TempCapacityVacInKbnumber:                      rand.Int63n(1000),
		MovingCapacityInKbnumber:                       rand.Int63n(1000),
		ActiveMovingCapacityInKbnumber:                 rand.Int63n(1000),
		PendingMovingCapacityInKbnumber:                rand.Int63n(1000),
		FwdRebuildCapacityInKbnumber:                   rand.Int63n(1000),
		ActiveFwdRebuildCapacityInKbnumber:             rand.Int63n(1000),
		PendingFwdRebuildCapacityInKb:                  rand.Int63n(1000),
		BckRebuildCapacityInKbnumber:                   rand.Int63n(1000),
		ActiveBckRebuildCapacityInKbnumber:             rand.Int63n(1000),
		PendingBckRebuildCapacityInKbnumber:            rand.Int63n(1000),
	}
	bytesData, _ := json.Marshal(data)
	return bytesData
}

func GetInstList() []string {
	var res []string
	for i := 0; i < 50; i++ {
		res = append(res, "instance"+fmt.Sprint(i))
	}
	return res
}
