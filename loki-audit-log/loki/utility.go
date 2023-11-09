package loki

import (
	"fmt"
	"regexp"
	"strings"
	"time"
)

func FormatQuery(query string, namespaces string, pod string) string {
	namespaceList := strings.Split(namespaces, ",")
	namespacePromStr := ""
	for _, namespace := range namespaceList {
		namespacePromStr += (namespace + "|")
	}
	namespacePromStr = namespacePromStr[:len(namespacePromStr)-1]
	return fmt.Sprintf(query, namespacePromStr, pod)
}

func WithinTimeRange(startTime time.Time, endTime time.Time, duration time.Duration) bool {
	return endTime.Sub(startTime) <= duration
}

func ProcessMultiLines(originData []*LokiLogData) []LokiLogData {
	var result []LokiLogData

	// Extract the Java exception logs
	OtherNormalLogs, JavaExceptionLogs := ProcessJavaMultiLines(originData)

	result = append(result, JavaExceptionLogs...)
	result = append(result, OtherNormalLogs...)
	return result
}

func ProcessJavaMultiLines(originData []*LokiLogData) ([]LokiLogData, []LokiLogData) {

	// Initialize the log cache
	logCache := LokiLogData{}
	logCache.Empty()

	// Initialize the regex for Java stack trace
	javaStackTraceExceptionRegex := regexp.MustCompile(`Exception:.*`)
	javaStackTraceAtRegex := regexp.MustCompile(`^\s*at.*\(*\)`)
	javaStackTraceCausedByRegex := regexp.MustCompile(`Caused by:`)

	// Initialize the result list
	var ExceptionMode = false
	var NormalLogs []LokiLogData
	var ExceptionLogs []LokiLogData
	originData = append(originData, &LokiLogData{})
	for _, logData := range originData {
		if logCache.IsEmpty() {
			logCache = *logData
			continue
		}

		// If current line is a Java stack trace line.
		if (javaStackTraceAtRegex.MatchString(logData.Text) ||
			javaStackTraceCausedByRegex.MatchString(logData.Text) ||
			javaStackTraceExceptionRegex.MatchString(logData.Text)) &&
			(logCache.IsSamePodAs(*logData) && WithinTimeRange(logCache.Timestamp, logData.Timestamp, time.Second*1)) {
			logCache.Text += "\n" + logData.Text
			ExceptionMode = true
			continue
		} else {
			// If the current line is not a Java stack trace line
			if ExceptionMode {
				// Send the previous error log and exit the exception mode
				ExceptionLogs = append(ExceptionLogs, logCache)
				ExceptionMode = false
			} else {
				// Send the previous normal log cache
				NormalLogs = append(NormalLogs, logCache)
			}
			logCache = *logData
		}

	}

	return NormalLogs, ExceptionLogs

}
