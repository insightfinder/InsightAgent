package insightfinder

import (
	"fmt"
	"strings"
)

func MakeBuckets[T any](data []T, bucketSize int) [][]T {
	var buckets [][]T

	for i := 0; i < len(data); i += bucketSize {
		end := i + bucketSize
		if end > len(data) {
			end = len(data)
		}
		buckets = append(buckets, data[i:end])
	}

	return buckets
}

func MakeSafeInstanceString(instance string, device string) string {
	str := strings.ReplaceAll(instance, "_", ".")
	str = strings.ReplaceAll(str, ",", ".")
	str = strings.ReplaceAll(str, ":", ".")
	str = strings.ReplaceAll(str, "[", "(")
	str = strings.ReplaceAll(str, "]", ")")

	if device != "" {
		str = fmt.Sprintf("%s_%s", str, MakeSafeInstanceString(device, ""))
	}

	return str
}
