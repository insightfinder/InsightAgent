package db

import "strings"

func getTableName(projectName string) string {
	return strings.ReplaceAll(projectName, "-", "_")
}
