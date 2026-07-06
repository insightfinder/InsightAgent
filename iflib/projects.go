package iflib

import (
	"context"
	"encoding/json"
	"fmt"
	"net/url"
	"strings"
)

// ProjectConfig describes a project to create or update.
type ProjectConfig struct {
	ProjectName        string `json:"projectName"`
	ProjectDisplayName string `json:"projectDisplayName,omitempty"`
	SystemName         string `json:"systemName"`
	// DataType: "Metric", "Log", "Alert", "Incident", "Deployment", "Trace"
	DataType string `json:"dataType"`
	// InstanceType: "PrivateCloud" or "OnPremise"
	InstanceType string `json:"instanceType"`
	// ProjectCloudType: "OnPremise", "ServiceNow", etc.
	ProjectCloudType string `json:"projectCloudType"`
	InsightAgentType string `json:"insightAgentType,omitempty"`
	SamplingInterval int    `json:"samplingInterval,omitempty"`
	// ServiceNowTable is only sent when ProjectCloudType is "ServiceNow".
	ServiceNowTable string `json:"-"`
}

// CheckProject returns true if the project exists in InsightFinder.
func (c *Client) CheckProject(ctx context.Context, projectName string) (bool, error) {
	form := url.Values{}
	form.Set("operation", "check")
	form.Set("projectName", projectName)

	body, status, err := c.doForm(ctx, "POST", "/api/v1/check-and-add-custom-project", form)
	if err != nil {
		return false, err
	}
	if status != 200 {
		return false, apiErr(status, body)
	}

	var resp struct {
		IsSuccess      bool   `json:"isSuccess"`
		IsProjectExist bool   `json:"isProjectExist"`
		Message        string `json:"message"`
	}
	if err := decodeJSON(body, &resp); err != nil {
		return false, fmt.Errorf("decode response: %w", err)
	}
	if !resp.IsSuccess {
		return false, fmt.Errorf("check project: %s", resp.Message)
	}
	return resp.IsProjectExist, nil
}

// CreateProject creates a new project. Returns nil if the project already exists.
func (c *Client) CreateProject(ctx context.Context, cfg ProjectConfig) error {
	form := url.Values{}
	form.Set("operation", "create")
	form.Set("projectName", cfg.ProjectName)
	form.Set("systemName", cfg.SystemName)
	form.Set("instanceType", cfg.InstanceType)
	form.Set("dataType", cfg.DataType)
	form.Set("projectCloudType", cfg.ProjectCloudType)
	if cfg.ProjectDisplayName != "" {
		form.Set("projectDisplayName", cfg.ProjectDisplayName)
	}
	if cfg.InsightAgentType != "" {
		form.Set("insightAgentType", cfg.InsightAgentType)
	}
	if cfg.SamplingInterval > 0 {
		form.Set("samplingInterval", fmt.Sprintf("%d", cfg.SamplingInterval))
	}
	if strings.EqualFold(cfg.ProjectCloudType, "ServiceNow") && cfg.ServiceNowTable != "" {
		form.Set("tableName", cfg.ServiceNowTable)
	}

	body, status, err := c.doForm(ctx, "POST", "/api/v1/check-and-add-custom-project", form)
	if err != nil {
		return err
	}

	if status == 400 {
		var resp struct {
			Success bool   `json:"success"`
			Message string `json:"message"`
		}
		if decodeJSON(body, &resp) == nil && !resp.Success {
			if strings.Contains(resp.Message, "already existed") || strings.Contains(resp.Message, "already exists") {
				return nil
			}
		}
		return apiErr(status, body)
	}

	if status != 200 {
		return apiErr(status, body)
	}

	var resp struct {
		Success bool   `json:"success"`
		Message string `json:"message"`
	}
	if err := decodeJSON(body, &resp); err != nil {
		return fmt.Errorf("decode response: %w", err)
	}
	if !resp.Success {
		return fmt.Errorf("create project: %s", resp.Message)
	}
	return nil
}

// EnsureProject creates the project only if it does not already exist.
func (c *Client) EnsureProject(ctx context.Context, cfg ProjectConfig) error {
	exists, err := c.CheckProject(ctx, cfg.ProjectName)
	if err != nil {
		return err
	}
	if exists {
		return nil
	}
	return c.CreateProject(ctx, cfg)
}

// GetProject retrieves a project's settings from the watch-tower-setting API.
// Returns nil, nil when the project does not exist.
func (c *Client) GetProject(ctx context.Context, projectName string) (map[string]any, error) {
	projectList, _ := json.Marshal([]map[string]string{
		{"projectName": projectName, "customerName": c.userName},
	})

	params := url.Values{}
	params.Set("projectList", string(projectList))

	body, status, err := c.doJSON(ctx, "GET", "/api/external/v1/watch-tower-setting", nil, params)
	if err != nil {
		return nil, err
	}
	if status == 404 || status == 204 {
		return nil, nil
	}
	if status != 200 {
		return nil, apiErr(status, body)
	}

	var response map[string]any
	if err := decodeJSON(body, &response); err != nil {
		return nil, fmt.Errorf("decode response: %w", err)
	}

	settingList, ok := response["settingList"].(map[string]any)
	if !ok || settingList[projectName] == nil {
		return nil, nil
	}

	settingsStr, ok := settingList[projectName].(string)
	if !ok {
		return nil, nil
	}

	var settingsWrapper map[string]any
	if err := decodeJSON([]byte(settingsStr), &settingsWrapper); err != nil {
		return nil, fmt.Errorf("decode project settings: %w", err)
	}

	// The actual settings live under the "DATA" key.
	if data, ok := settingsWrapper["DATA"].(map[string]any); ok {
		return data, nil
	}
	return settingsWrapper, nil
}

// UpdateProject updates project settings via the watch-tower-setting API.
// settings is a map of field names to values (e.g. {"cValue": 3, "retentionTime": 90}).
func (c *Client) UpdateProject(ctx context.Context, projectName string, settings map[string]any) error {
	params := url.Values{}
	params.Set("projectName", projectName)
	params.Set("customerName", c.userName)

	body, status, err := c.doJSON(ctx, "POST", "/api/external/v1/watch-tower-setting", settings, params)
	if err != nil {
		return err
	}
	if status != 200 {
		return apiErr(status, body)
	}
	return nil
}

// DeleteProject deletes a project.
func (c *Client) DeleteProject(ctx context.Context, projectName string) error {
	form := url.Values{}
	form.Set("projectName", projectName)

	body, status, err := c.doForm(ctx, "POST", "/api/v1/delete-project", form)
	if err != nil {
		return err
	}
	// 404/405 means the project is already gone or deletion is not supported.
	if status == 404 || status == 405 {
		return nil
	}
	if status != 200 {
		return apiErr(status, body)
	}

	var resp struct {
		Success bool   `json:"success"`
		Message string `json:"message"`
	}
	if err := decodeJSON(body, &resp); err != nil {
		return fmt.Errorf("decode response: %w", err)
	}
	if !resp.Success {
		return fmt.Errorf("delete project: %s", resp.Message)
	}
	return nil
}

// GetProjectMode returns the processing mode for a log project.
// 0 = batch, 1 = streaming / dedicated, 2 = near-real-time.
// Uses legacy Cookie auth required by /api/v1/logdedicatedmode.
func (c *Client) GetProjectMode(ctx context.Context, projectName string) (int, error) {
	params := url.Values{}
	params.Set("userName", c.userName)
	params.Set("projectName", projectName)
	params.Set("licenseKey", c.licenseKey)

	body, status, err := c.doCookie(ctx, "GET", "/api/v1/logdedicatedmode", params)
	if err != nil {
		return 0, err
	}
	if status == 404 || status == 204 {
		return 0, nil
	}
	if status != 200 {
		return 0, apiErr(status, body)
	}

	var resp struct {
		Success bool `json:"success"`
		Data    []struct {
			ProcessMode int `json:"processMode"`
		} `json:"data"`
	}
	if err := decodeJSON(body, &resp); err != nil {
		return 0, fmt.Errorf("decode response: %w", err)
	}
	if !resp.Success || len(resp.Data) == 0 {
		return 0, nil
	}
	return resp.Data[0].ProcessMode, nil
}

// SetProjectMode sets the processing mode for a log project.
// Uses legacy Cookie auth required by /api/v1/logdedicatedmode.
func (c *Client) SetProjectMode(ctx context.Context, projectName string, mode int) error {
	params := url.Values{}
	params.Set("userName", c.userName)
	params.Set("projectName", projectName)
	params.Set("mode", fmt.Sprintf("%d", mode))
	params.Set("licenseKey", c.licenseKey)

	body, status, err := c.doCookie(ctx, "POST", "/api/v1/logdedicatedmode", params)
	if err != nil {
		return err
	}
	if status != 200 {
		return apiErr(status, body)
	}

	var resp struct {
		Success bool   `json:"success"`
		Message string `json:"message,omitempty"`
	}
	if err := decodeJSON(body, &resp); err != nil {
		return fmt.Errorf("decode response: %w", err)
	}
	if !resp.Success {
		return fmt.Errorf("set project mode: %s", resp.Message)
	}
	return nil
}

// JsonKeyType describes the type configuration for a JSON key in a log project.
type JsonKeyType struct {
	JsonKey        string `json:"jsonKey"`
	Type           string `json:"type"`
	SummaryCheck   bool   `json:"summaryCheck"`
	MetaFieldCheck bool   `json:"metaFieldCheck"`
}

// GetJsonKeyTypes returns the JSON key type configurations for a project.
func (c *Client) GetJsonKeyTypes(ctx context.Context, projectName string) ([]JsonKeyType, error) {
	params := url.Values{}
	params.Set("projectName", fmt.Sprintf("%s@%s", projectName, c.userName))

	body, status, err := c.doJSON(ctx, "GET", "/api/external/v1/logjsontype", nil, params)
	if err != nil {
		return nil, err
	}
	if status == 404 {
		return []JsonKeyType{}, nil
	}
	if status != 200 {
		return nil, apiErr(status, body)
	}

	var keys []JsonKeyType
	if err := decodeJSON(body, &keys); err != nil {
		return nil, fmt.Errorf("decode response: %w", err)
	}
	return keys, nil
}

// UpdateJsonKeyTypes updates the JSON key type configurations for a project.
func (c *Client) UpdateJsonKeyTypes(ctx context.Context, projectName string, keys []JsonKeyType) error {
	if len(keys) == 0 {
		return nil
	}
	keysJSON, err := json.Marshal(keys)
	if err != nil {
		return fmt.Errorf("marshal keys: %w", err)
	}

	form := url.Values{}
	form.Set("projectName", fmt.Sprintf("%s@%s", projectName, c.userName))
	form.Set("jsonTypes", string(keysJSON))

	body, status, err := c.doForm(ctx, "POST", "/api/external/v1/logjsontype", form)
	if err != nil {
		return err
	}
	if status != 200 {
		return apiErr(status, body)
	}
	return nil
}

// NotificationSetting represents a single notification channel entry.
type NotificationSetting struct {
	Selected    bool   `json:"selected"`
	DisplayName string `json:"displayName"`
}

// ServiceNowNotificationAdditionalSetting holds ServiceNow-specific notification format strings.
type ServiceNowNotificationAdditionalSetting struct {
	ShortDescriptionFormat string `json:"shortDescriptionFormat"`
	DescriptionFormat      string `json:"descriptionFormat"`
}

// JsonKeySummarySettings describes log summary field settings for a project.
type JsonKeySummarySettings struct {
	SummarySetting                          []string                                 `json:"summarySetting"`
	MetaFieldSetting                        []string                                 `json:"metaFieldSetting"`
	DampeningFieldSetting                   []string                                 `json:"dampeningFieldSetting"`
	NotificationSetting                     map[string]NotificationSetting           `json:"notificationSetting"`
	ServiceNowNotificationSetting           map[string]NotificationSetting           `json:"serviceNowNotificationSetting"`
	ServiceNowNotificationAdditionalSetting *ServiceNowNotificationAdditionalSetting `json:"serviceNowNotificationAdditionalSetting,omitempty"`
}

// GetJsonKeySummarySettings returns the log summary/metafield settings for a project.
func (c *Client) GetJsonKeySummarySettings(ctx context.Context, projectName string) (*JsonKeySummarySettings, error) {
	params := url.Values{}
	params.Set("projectName", fmt.Sprintf("%s@%s", projectName, c.userName))

	body, status, err := c.doJSON(ctx, "GET", "/api/external/v1/logsummarysettings", nil, params)
	if err != nil {
		return nil, err
	}
	if status == 404 {
		return &JsonKeySummarySettings{}, nil
	}
	if status != 200 {
		return nil, apiErr(status, body)
	}

	var settings JsonKeySummarySettings
	if err := decodeJSON(body, &settings); err != nil {
		return nil, fmt.Errorf("decode response: %w", err)
	}
	return &settings, nil
}

// UpdateJsonKeySummarySettings updates the log summary/metafield settings for a project.
func (c *Client) UpdateJsonKeySummarySettings(ctx context.Context, projectName string, settings JsonKeySummarySettings) error {
	params := url.Values{}
	params.Set("projectName", fmt.Sprintf("%s@%s", projectName, c.userName))

	body, status, err := c.doJSON(ctx, "POST", "/api/external/v1/logsummarysettings", settings, params)
	if err != nil {
		return err
	}
	if status != 200 {
		return apiErr(status, body)
	}
	return nil
}
