package insightfinder

import (
	"fmt"
	"github.com/rs/zerolog/log"
	"github.com/samber/lo"
	"net/url"
	"os"
	"path"
	"path/filepath"
	"strconv"
	"strings"
)

func SplitString(input string, sep string) []string {
	return lo.Filter(strings.Split(input, sep), func(s string, idx int) bool {
		return strings.TrimSpace(s) != ""
	})
}

func AlignTimestamp(timestamp int64, interval int) int64 {
	return timestamp - (timestamp % int64(interval))
}

func ToString(inputVar interface{}) string {
	if inputVar == nil {
		return ""
	}
	return fmt.Sprint(inputVar)
}

func ToBool(inputVar interface{}) (boolValue bool) {
	if inputVar == nil || inputVar == "" {
		return false
	}
	switch castedVal := inputVar.(type) {
	case string:
		var err error
		if strings.ToLower(castedVal) == "yes" {
			return true
		} else if strings.ToLower(castedVal) == "no" {
			return false
		}

		boolValue, err = strconv.ParseBool(castedVal)
		if err != nil {
			panic("Wrong input type. Can not convert current input to boolean.")
		}
	case bool:
		boolValue = castedVal
	}
	return boolValue
}

func ToInt(inputVar interface{}) int {
	if inputVar == nil {
		return 0
	}
	switch castedVal := inputVar.(type) {
	case string:
		intValue, err := strconv.Atoi(castedVal)
		if err != nil {
			panic("Wrong input type. Can not convert current input to int.")
		}
		return intValue
	case int:
		return castedVal
	}
	return 0
}

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

func AbsFilePath(filename string) string {
	if filename == "" {
		filename = ""
	}
	curdir, err := os.Getwd()
	if err != nil {
		panic(err)
	}
	mydir, err := filepath.Abs(curdir)
	if err != nil {
		panic(err)
	}
	return filepath.Join(mydir, filename)
}

func BuildCompleteURL(baseUrl string, endpoint string) string {
	postUrl, err := url.Parse(baseUrl)
	if err != nil {
		log.Warn().Msgf("Fail to pares the URL %s. Please check your config.", baseUrl)
		panic(err)
	}

	postUrl.Path = path.Join(postUrl.Path, endpoint)
	return postUrl.String()
}
