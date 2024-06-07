package jaeger_client

func GetTagValue(key string, tags *map[string]StringOrBool) string {
	if value, ok := (*tags)[key]; ok {
		return string(value)
	}
	return ""
}

func GetFirstTagValue(tagsToSearch []string, allTags *map[string]StringOrBool) string {
	for _, tag := range tagsToSearch {
		value := GetTagValue(tag, allTags)
		if value != "" {
			return value
		}
	}
	return ""
}
