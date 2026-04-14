package insightfinder

import (
	"regexp"
	"strings"
)

// CleanDeviceName sanitises a device/instance name the same way loki-agent does.
func CleanDeviceName(name string) string {
	if name == "" {
		return name
	}
	name = strings.ReplaceAll(name, "_", ".")
	name = strings.ReplaceAll(name, ":", "-")
	name = strings.ReplaceAll(name, "/", ".")

	re := regexp.MustCompile(`^[-_\W]+`)
	cleaned := strings.TrimSpace(re.ReplaceAllString(name, ""))
	if cleaned == "" {
		return name
	}
	return cleaned
}
