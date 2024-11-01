package worker

func ExtractFirstAvailLabel(findList *[]string, labels *map[string]string) string {

	if labels == nil {
		return ""
	}

	if findList == nil || len(*findList) == 0 {
		return ""
	}

	for _, toBeFound := range *findList {
		result := (*labels)[toBeFound]
		if result != "" {
			return result
		}
	}
	return ""
}
