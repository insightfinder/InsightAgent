package jaeger

import (
	"context"
	"github.com/carlmjohnson/requests"
)

type Jaeger struct {
	Endpoint string
	Username string
	Password string
}

// Func: GetDAG
func (jaeger *Jaeger) GetDAG() *[]DependencyData {
	url := jaeger.Endpoint + "/api/dependencies"
	response := DependencyResponseBody{}
	err := requests.URL(url).BasicAuth(jaeger.Username, jaeger.Password).ToJSON(&response).Accept("application/json").UserAgent("Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:109.0) Gecko/20100101 Firefox/119.0").Fetch(context.Background())
	if err != nil {
		println(err.Error())
	}
	return &response.Data
}
