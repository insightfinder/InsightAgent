package jaeger_client

func GetTagValue(key string, tags *[]Tag) string {
	for _, tag := range *tags {
		if tag.Key == key {
			return string(tag.Value)
		}
	}
	return ""
}

func GetFirstTagValue(tagsToSearch []string, allTags *[]Tag) string {
	for _, tag := range tagsToSearch {
		value := GetTagValue(tag, allTags)
		if value != "" {
			return value
		}
	}
	return ""
}
