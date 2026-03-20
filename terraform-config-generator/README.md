# Terraform Configuration Generator

Generates Terraform HCL files for InsightFinder projects, enabling IaC management of all project settings including log labels, JSON keys, ServiceNow integration, and system-level KB/notification settings.

---

## Scripts

| Script | Purpose |
|--------|---------|
| `auto_generate_terraform.py` | **Fully automated** — reads `config.yaml`, discovers all owned systems and projects via API, generates the complete `TerraformFiles/` directory structure |
| `fetch_insightfinder_data.py` | Fetches raw API data for a single project and saves to JSON files |
| `generate_terraform_cli.py` | Generates a `.tf` file from previously fetched JSON files |

---

## Requirements

```bash
pip install requests pyyaml
```

- Python 3.10+
- Terraform >= 1.0
- InsightFinder Terraform Provider >= 1.6.1 (version constraint set via `terraform_version` in config)

---

## Automated Generation (Recommended)

### 1. Configure `config.yaml`

```yaml
Delay: 2  # seconds between project API calls (0 = no delay)

STAGING:
  base_url: https://stg.insightfinder.com/
  username: yourUsername
  licensekey: YOUR_LICENSE_KEY
  project_types: [log]        # log, metric, alert, trace
  terraform_version: 1.7.0   # optional; written into versions.tf (default: ">= 1.6.1")

PROD:
  base_url: https://app.insightfinder.com/
  username: yourUsername
  licensekey: YOUR_LICENSE_KEY
  project_types: [log, metric]
  terraform_version: 1.7.0
  only_process:               # optional; omit to process all owned systems/projects
    systems: ["System A"]     # process ALL projects in these systems
    projects: ["Project C"]   # also process these specific projects (uses their original system folder)
```

#### `terraform_version`

Sets the provider version constraint written into each `versions.tf`:

```hcl
insightfinder = {
  source  = "insightfinder/insightfinder"
  version = "1.7.0"           # taken from terraform_version in config
}
```

If omitted, the default constraint `>= 1.6.1` is used.

#### `only_process`

Limits which systems and projects are generated. Both fields are optional and can be used together or independently.

| Field | Behaviour |
|-------|-----------|
| `systems` | Process **all** projects (matching `project_types`) inside the listed systems |
| `projects` | Process these specific projects regardless of which system they belong to; the original system's folder structure is preserved |

**Examples:**

```yaml
# Only two specific projects, no system restriction
only_process:
  projects: ["Project A", "Project B"]

# All projects in System A, plus one extra project from any other system
only_process:
  systems: ["System A"]
  projects: ["Project C"]
```

If `only_process` is omitted entirely, all owned systems and projects are processed (existing behaviour).

### 2. Run

```bash
# All environments
python3 auto_generate_terraform.py --config config.yaml

# Single environment
python3 auto_generate_terraform.py --config config.yaml --env STAGING

# Preview without writing files
python3 auto_generate_terraform.py --config config.yaml --dry-run

# Custom output directory
python3 auto_generate_terraform.py --config config.yaml --output-dir /path/to/output
```

The script will:
- Discover all **owned** systems (`ownSystemArr`) for each environment
- Filter projects by the configured `project_types` (matched against API `dataType`)
- Fetch all settings per project (keywords, watch-tower settings, summary/metafields, JSON keys, ServiceNow)
- Fetch system-level settings (knowledgebase, incident prediction, notifications)
- Write the full directory structure and run `terraform fmt -recursive` at the end

### Generated Structure

```
TerraformFiles/
└── STAGING/
    └── My System/
        ├── versions.tf          # provider version lock + S3 backend
        ├── provider.tf          # insightfinder provider block
        ├── variables.tf         # all input variables
        ├── terraform.tfvars     # base_url, system_name, servicenow_host
        ├── projects.tf          # module call to ./projects
        ├── system_settings.tf   # KB + notification settings (var.system_name)
        └── projects/
            ├── versions.tf      # provider source reference (no version)
            ├── variables.tf     # system_name + servicenow vars
            ├── project_one.tf
            ├── project_two.tf
            └── ...
```

---

## Manual Single-Project Generation

Use this when you need to regenerate one specific project.

### 1. Fetch project data

```bash
python3 fetch_insightfinder_data.py \
  --username yourUsername \
  --api-key YOUR_KEY \
  --customer-name yourUsername \
  --project-name "my-project" \
  --system-name "My System" \
  --host https://app.insightfinder.com
```

This saves: `sample_settings.json`, `sample_keywords.json`, `sample_jsonkey.json`, `sample_summary_and_metafields.json`, `sample_servicenow.json`, `sample_kb_global.json`, `sample_kb_incident_prediction.json`, `sample_notifications.json`

### 2. Generate `.tf` file

```bash
python3 generate_terraform_cli.py \
  --settings sample_settings.json \
  --keywords sample_keywords.json \
  --json-keys sample_jsonkey.json \
  --summary-metafield sample_summary_and_metafields.json \
  --system-name "My System" \
  --base-url https://app.insightfinder.com \
  --output my_project.tf
```

With ServiceNow:
```bash
python3 generate_terraform_cli.py \
  --settings sample_settings.json \
  --keywords sample_keywords.json \
  --servicenow sample_servicenow.json \
  --system-name "My System" \
  --output my_project.tf
```

With system-level settings:
```bash
python3 generate_terraform_cli.py \
  --settings sample_settings.json \
  --keywords sample_keywords.json \
  --system-name "My System" \
  --kb-global sample_kb_global.json \
  --kb-incident-prediction sample_kb_incident_prediction.json \
  --notifications sample_notifications.json \
  --output my_project.tf
```
---

## Troubleshooting

```bash
# Validate generated files
terraform validate

# Check JSON files are valid
python3 -m json.tool sample_settings.json

# SSL issues (self-signed certs)
python3 auto_generate_terraform.py --config config.yaml --no-ssl-verify
```
