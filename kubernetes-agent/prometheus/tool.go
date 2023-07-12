package prometheus

import (
	"fmt"
	"time"
)

func convertToFloatTimeStamp(time time.Time) string {
	return fmt.Sprintf("%.3f", time.UnixMilli())
}
