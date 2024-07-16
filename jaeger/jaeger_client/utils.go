package jaeger_client

import "strconv"

func GetTagValue(key string, tags *map[string]any) string {
	if value, ok := (*tags)[key]; ok {
		return ToString(value)
	}
	return ""
}

func GetFirstTagValue(tagsToSearch []string, allTags *map[string]any) string {
	for _, tag := range tagsToSearch {
		value := GetTagValue(tag, allTags)
		if value != "" {
			return value
		}
	}
	return ""
}
func ToString(value any) string {
	switch v := value.(type) {
	case string:
		return v
	case bool:
		return strconv.FormatBool(v)
	case int:
		return strconv.Itoa(v)
	case int64:
		return strconv.FormatInt(v, 10)
	case float64:
		return strconv.FormatFloat(v, 'f', -1, 64)
	default:
		return ""
	}
}
