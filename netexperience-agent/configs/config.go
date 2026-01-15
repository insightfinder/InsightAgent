package config

import (
	"fmt"
	"os"

	"gopkg.in/yaml.v2"
)

func LoadConfig(path string) (*Config, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("error reading config file: %w", err)
	}

	var cfg Config
	if err := yaml.Unmarshal(data, &cfg); err != nil {
		return nil, fmt.Errorf("error parsing config file: %w", err)
	}

	// Set defaults if not specified
	if cfg.NetExperience.TokenRefreshInterval == 0 {
		cfg.NetExperience.TokenRefreshInterval = 82800 // 23 hours
	}
	if cfg.NetExperience.TokenRetryAttempts == 0 {
		cfg.NetExperience.TokenRetryAttempts = 3
	}
	if cfg.NetExperience.TokenRetryDelay == 0 {
		cfg.NetExperience.TokenRetryDelay = 5
	}
	if cfg.NetExperience.RateLimitRequests == 0 {
		cfg.NetExperience.RateLimitRequests = 180
	}
	if cfg.NetExperience.RateLimitPeriod == 0 {
		cfg.NetExperience.RateLimitPeriod = 10
	}
	if cfg.NetExperience.MaxConcurrentRequests == 0 {
		cfg.NetExperience.MaxConcurrentRequests = 5
	}
	if cfg.NetExperience.EquipmentBatchSize == 0 {
		cfg.NetExperience.EquipmentBatchSize = 5
	}
	if cfg.NetExperience.CustomerCacheRefreshHours == 0 {
		cfg.NetExperience.CustomerCacheRefreshHours = 24
	}
	if cfg.NetExperience.EquipmentCacheRefreshHours == 0 {
		cfg.NetExperience.EquipmentCacheRefreshHours = 24
	}
	if cfg.NetExperience.MinClientsRSSIThreshold == 0 {
		cfg.NetExperience.MinClientsRSSIThreshold = 10
	}
	if cfg.InsightFinder.SamplingInterval == 0 {
		cfg.InsightFinder.SamplingInterval = 60
	}

	return &cfg, nil
}

func SaveConfig(path string, cfg *Config) error {
	data, err := yaml.Marshal(cfg)
	if err != nil {
		return fmt.Errorf("error marshaling config: %w", err)
	}

	if err := os.WriteFile(path, data, 0644); err != nil {
		return fmt.Errorf("error writing config file: %w", err)
	}

	return nil
}
