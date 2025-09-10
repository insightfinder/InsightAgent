# Jira Maintenance Window Agent

A Python script that connects to Jira using API credentials, applies configurable filters, and extracts ticket metadata based on status criteria.

## Features

- Connect to Jira Cloud or Server using API token authentication
- Filter tickets using existing Jira filters (by name or ID)
- Apply additional status-based filtering (include/exclude specific statuses)
- Export results in JSON, CSV, or console format
- Configurable field extraction
- Comprehensive logging
- Command-line interface with various options

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Settings

Copy the template configuration file and update it with your settings:

```bash
cp conf.d/config.ini.template conf.d/config.ini
```

Edit `conf.d/config.ini` with your Jira details:

```ini
[jira]
url = https://your-company.atlassian.net
api_token = your_api_token_here
username = your_email@company.com

[filter]
filter_name = All work items

[status_filter]
mode = exclude
statuses = Closed, Cancelled
```

### 3. Get Jira API Token

For Jira Cloud:
1. Go to https://id.atlassian.com/manage-profile/security/api-tokens
2. Click "Create API token"
3. Copy the token and paste it in your config.ini

For Jira Server:
- Use your password instead of an API token

## Configuration Options

### [jira] section
- `url`: Your Jira instance URL
- `api_token`: API token or password
- `username`: Your email (for Cloud) or username (for Server)

### [filter] section
- `filter_name`: Name of the Jira filter to use (e.g., "All work items")
- `filter_id`: Alternative to filter_name, use the filter ID directly

### [status_filter] section
- `mode`: Either "exclude" or "include"
  - `exclude`: Get tickets that are NOT in the specified statuses
  - `include`: Get tickets that ARE in the specified statuses
- `statuses`: Comma-separated list of status names (case insensitive)

### [type_filter] section
- `mode`: Either "exclude" or "include" (optional, leave empty to disable)
  - `exclude`: Get tickets that are NOT of the specified types
  - `include`: Get tickets that ARE of the specified types
- `types`: Comma-separated list of issue type names (case insensitive)

Available issue types in your system:
- `Onsite Service: Repair & Maintenance Project`
- `Device Incident`
- `Problem`
- `Task`
- `Onsite Technician Dispatch`
- `Park Notes and Maintenance`
- `Epitiro Alert`
- `Vendor Support`
- `Onsite Service: New Implementation`

### [output] section
- `format`: Output format - "json", "csv", or "console"
- `output_file`: File path to save results (optional)
- `fields`: Comma-separated list of fields to extract

Available fields:
- `key`: Issue key (e.g., PROJ-123)
- `summary`: Issue title/summary
- `status`: Current status
- `assignee`: Assigned person
- `reporter`: Person who created the issue
- `created`: Creation date
- `updated`: Last update date
- `priority`: Priority level
- `description`: Issue description
- `components`: Components list
- `labels`: Labels list
- `resolution`: Resolution status
- `issuetype`: Type of issue
- `project`: Project key

### [logging] section
- `level`: Log level (DEBUG, INFO, WARNING, ERROR)
- `log_file`: Path to log file (optional)

## Example Configurations

### Example 1: Filter for Open Bug Reports
```ini
[status_filter]
operation = exclude
statuses = Done, Closed, Resolved

[type_filter]
operation = include
types = Bug
```

### Example 2: Get All Stories Except Cancelled
```ini
[status_filter]
operation = exclude
statuses = Cancelled, Canceled

[type_filter]
operation = include
types = Story, User Story
```

### Example 3: Maintenance Projects Only
```ini
[status_filter]
operation = exclude
statuses = Closed: Appointment Occurred, Closed, Canceled, Done, Completed, ISP RFO Pending, Internal RFO Pending

[type_filter]
operation = include
types = Onsite Service: Repair & Maintenance Project
```

## Usage

### Basic Usage

Run with default configuration:
```bash
python jira_agent.py
```

### Test Connection

Test your Jira connection:
```bash
python jira_agent.py --test-connection
```

### List Available Filters

See what filters you have access to:
```bash
python jira_agent.py --list-filters
```

### Custom Configuration File

Use a different configuration file:
```bash
python jira_agent.py --config /path/to/custom/config.ini
```

### Command Line Options

```
usage: jira_agent.py [-h] [--config CONFIG] [--test-connection] [--list-filters]

options:
  -h, --help            show this help message and exit
  --config CONFIG, -c CONFIG
                        Path to configuration file (default: conf.d/config.ini)
  --test-connection     Test connection to Jira and exit
  --list-filters        List available filters and exit
```

## Example Configurations

### Example 1: Get all open tickets
```ini
[status_filter]
mode = exclude
statuses = Closed, Done, Resolved, Cancelled
```

### Example 2: Get only tickets in progress
```ini
[status_filter]
mode = include
statuses = In Progress, In Review
```

### Example 3: Export to CSV with specific fields
```ini
[output]
format = csv
output_file = open_tickets.csv
fields = key, summary, status, assignee, priority, created
```

## Output Examples

### JSON Output
```json
[
  {
    "key": "PROJ-123",
    "summary": "Fix login issue",
    "status": "In Progress",
    "assignee": "John Doe",
    "created": "2025-08-01T10:00:00.000+0000",
    "priority": "High"
  }
]
```

### Console Output
```
================================================================================
JIRA TICKETS SUMMARY - 2025-08-27 15:30:45
================================================================================
Total tickets found: 5

1. PROJ-123 - Fix login issue
   Status: In Progress
   Assignee: John Doe
   Created: 2025-08-01T10:00:00.000+0000
----------------------------------------
```

## Error Handling

The script includes comprehensive error handling:
- Connection failures
- Authentication errors
- Invalid filter names
- API rate limiting
- Network timeouts

Check the log file or console output for detailed error information.

## Troubleshooting

### Common Issues

1. **Authentication Failed**
   - Verify your API token is correct
   - Check that your username/email is correct
   - Ensure you have permission to access the Jira instance

2. **Filter Not Found**
   - Use `--list-filters` to see available filters
   - Check that the filter name matches exactly (case-insensitive)
   - Verify you have permission to access the filter

3. **No Results**
   - Check your status filter configuration
   - Verify the base filter has results
   - Use console output format to debug

4. **Connection Issues**
   - Verify the Jira URL is correct
   - Check network connectivity
   - Ensure your firewall allows HTTPS connections

### Debug Mode

Enable debug logging for more detailed information:
```ini
[logging]
level = DEBUG
log_file = debug.log
```

## Security Notes

- Store your API token securely
- Don't commit config.ini to version control
- Use environment variables for sensitive data in production
- Regularly rotate your API tokens

## License

This script is provided as-is for educational and operational purposes.
