package jaeger_client

func GetTagValue(key string, tags *[]Tag) string {
	for _, tag := range *tags {
		if tag.Key == key {
			return string(tag.Value)
		}
	}
	return ""
}
