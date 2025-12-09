package sampler

import (
	"github.com/insightfinder/receiver-agent/configs"
)

// SamplerService represents the periodic sampler service
type SamplerService struct {
	config    *configs.SamplerConfig
	appConfig *configs.Config
	stopChan  chan struct{}
}
