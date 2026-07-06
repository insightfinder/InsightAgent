package iflib

import (
	"context"
	"net/url"
)

// ThirdPartyInstanceEntry is one instance entry for /api/v1/agent-upload-third-party-instancemetadata.
type ThirdPartyInstanceEntry struct {
	InstanceName string                `json:"instanceName"`
	JiraConfigs  ThirdPartyJiraConfigs `json:"jiraConfigs"`
}

// ThirdPartyJiraConfigs wraps Jira custom-field values for one instance.
// Each key is a Jira custom field ID (e.g. "customfield_10060") and the value is
// formatted as "{workspaceID}:{objectID}".
type ThirdPartyJiraConfigs struct {
	JiraIssueFields map[string]string `json:"jiraIssueFields"`
}

// UploadThirdPartyInstanceMetadata sends Jira asset metadata (venue/subvenue IDs, etc.)
// for the given instances in projectName to InsightFinder.
// Entries with no JiraIssueFields are silently skipped.
func (c *Client) UploadThirdPartyInstanceMetadata(ctx context.Context, projectName string, entries []ThirdPartyInstanceEntry) error {
	if len(entries) == 0 {
		return nil
	}

	params := url.Values{}
	params.Set("customerName", c.userName)
	params.Set("licenseKey", c.licenseKey)
	params.Set("projectName", projectName)

	body, status, err := c.doJSON(ctx, "POST", "/api/v1/agent-upload-third-party-instancemetadata", entries, params)
	if err != nil {
		return err
	}
	if status != 200 {
		return apiErr(status, body)
	}
	return nil
}
