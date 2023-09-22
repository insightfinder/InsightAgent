package prometheus

import (
	"fmt"
	"strings"
)

func FormatQueryWithNamespaces(query string, namespaces string) string {
	if strings.Contains(query, "namespace=") {
		namespaceList := strings.Split(namespaces, ",")
		namespacePromStr := ""
		for _, namespace := range namespaceList {
			namespacePromStr += (namespace + "|")
		}
		namespacePromStr = namespacePromStr[:len(namespacePromStr)-1]
		return fmt.Sprintf(query, namespacePromStr)
	}
	return query
}
