# Terraform Configuration Generator

This tool generates Terraform configuration files from InsightFinder API data, enabling Infrastructure as Code (IaC) management of InsightFinder projects.

## Overview

The `generate_terraform_cli.py` script converts InsightFinder project settings and keywords into Terraform HCL format, supporting all project configuration options including log label settings, ServiceNow integration, and advanced detection settings.

## Requirements

- Python 3.6 or higher
- Terraform >= 1.0
- InsightFinder Terraform Provider >= 1.0.0

## Getting Data from InsightFinder UI

To export your existing project configuration from InsightFinder:

### 1. Navigate to Project Settings
- Log in to your InsightFinder instance
- Go to your project's settings page

### 2. Open Browser Developer Tools
- Press **F12** to open browser developer tools
- Go to the **Network** tab

### 3. Copy API Responses

**For Project Settings (`sample_settings.json`):**
- Find the API call: `/api/v2/project-setting` (GET)
- Copy the response JSON

**For Keywords (`sample_keywords.json`):**
- Find the API call: `/api/v1/projectkeywords` (GET)
- Copy the response JSON

**For ServiceNow Settings (`sample_servicenow.json`):**
- Find the API call: `/api/v2/thirdpartysetting` (GET)
- Copy the response JSON

### 4. Save to Files
Save each copied response to the corresponding JSON file.

## Quick Start

### 1. Prepare Input Files

Create three JSON files with your project configuration:
- `sample_settings.json` - Project settings
- `sample_keywords.json` - Log label keywords
- `sample_servicenow.json` - ServiceNow settings (optional)

### 2. Generate Terraform Configuration

Basic usage:
```bash
python3 generate_terraform_cli.py \
  --settings sample_settings.json \
  --keywords sample_keywords.json
```

With ServiceNow integration:
```bash
python3 generate_terraform_cli.py \
  --settings sample_settings.json \
  --keywords sample_keywords.json \
  --servicenow sample_servicenow.json
```

### 3. Apply Configuration

```bash
terraform init
terraform plan
terraform apply
```

## Usage Options

### Specify Output File

```bash
python3 generate_terraform_cli.py \
  --settings sample_settings.json \
  --keywords sample_keywords.json \
  --output myproject.tf
```

### Override Project Details

```bash
python3 generate_terraform_cli.py \
  --settings sample_settings.json \
  --keywords sample_keywords.json \
  --project-name "My Project" \
  --system-name "Production"
```

### Append to Existing File

```bash
python3 generate_terraform_cli.py \
  --settings sample_settings.json \
  --keywords sample_keywords.json \
  --output existing.tf \
  --no-provider
```

### Custom Base URL

```bash
python3 generate_terraform_cli.py \
  --settings sample_settings.json \
  --keywords sample_keywords.json \
  --base-url "https://app.insightfinder.com"
```

## Input File Formats

### Settings JSON
```json
{
  "settingList": {
    "ProjectName": "{\"CLASSNAME\":\"...\",\"DATA\":{...}}"
  }
}
```

### Keywords JSON
```json
{
  "keywords": {
    "whitelist": [],
    "featurelist": [...],
    "incidentlist": [...]
  }
}
```

### ServiceNow JSON
```json
{
  "host": "https://your-instance.service-now.com",
  "serviceNowUser": "username",
  "serviceNowPassword": "password",
  "instanceField": "test_ci"
}
```

See sample files for complete examples.

## Command-Line Options

| Option | Required | Description |
|--------|----------|-------------|
| `--settings` | Yes | Path to settings JSON file |
| `--keywords` | Yes | Path to keywords JSON file |
| `--servicenow` | No | Path to ServiceNow settings JSON file |
| `--output`, `-o` | No | Output Terraform file (default: auto-generated) |
| `--project-name` | No | Override project name from settings |
| `--system-name` | No | System name (default: "Default System") |
| `--base-url` | No | InsightFinder base URL (default: https://stg.insightfinder.com) |
| `--no-provider` | No | Skip provider block for appending to existing files |
| `--help`, `-h` | No | Show help message |

## Output

The script generates a Terraform configuration file containing:

1. **Provider Configuration** (unless `--no-provider` is used)
2. **Project Resource** with all settings
3. **Log Label Settings** (if keywords provided)
4. **ServiceNow Settings** (if ServiceNow JSON provided)

## Troubleshooting

### Validate JSON Files
```bash
python3 -m json.tool sample_settings.json
python3 -m json.tool sample_keywords.json
```

### Check Generated File
```bash
cat output.tf
terraform validate
```

## License

This tool is provided as-is for use with InsightFinder.
