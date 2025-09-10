# Zabbix Host Group Config Generator

This script automatically generates individual `.ini` configuration files for each Zabbix host group, using the `config.ini.template` as a Jinja2 template.

## Features

- Connects to Zabbix and retrieves all host groups
- Checks for existing `.ini` files in the `conf.d` directory
- Creates missing `.ini` files using the template
- Sanitizes host group names for filename compatibility
- Preserves original host group names in the file content
- Avoids overwriting existing files

## Filename Convention

The script follows this naming convention:
- **Original host group name**: `-Valley Rose RV Park`
- **Sanitized filename**: `-Valley-Rose-RV-Park-metrics.ini`

**Sanitization rules**:
- Whitespace and special characters are replaced with hyphens (`-`)
- Multiple consecutive hyphens are merged into single hyphens
- Leading and trailing hyphens are removed
- The suffix `-metrics.ini` is added

## Configuration

Edit the `ZABBIX_CONFIG` section at the top of the `generate_hostgroup_configs.py` script:

```python
ZABBIX_CONFIG = {
    'url': 'http://your-zabbix-server:80',
    'user': 'your-username', 
    'password': 'your-password',
    'request_timeout': 60
}
```

Also configure the paths if needed:
```python
TEMPLATE_FILE = "conf.d/config.ini.template"
OUTPUT_DIR = "conf.d"
INI_SUFFIX = "-metrics.ini"
```

## Requirements

- Python 3.x
- pyzabbix library
- jinja2 library
- Valid Zabbix server access
- `conf.d/config.ini.template` file

## Usage

### Basic Usage

```bash
# Generate .ini files for all missing host groups
python generate_hostgroup_configs.py
```

The script will:
1. Connect to Zabbix and fetch all host groups
2. Check which `.ini` files already exist in `conf.d/`
3. Create missing `.ini` files using the template
4. Display a summary of the operation

### Example Output

```
Starting Zabbix Host Group .ini File Generator
Template file: conf.d/config.ini.template
Output directory: conf.d
Zabbix server: http://localhost:9999/zabbix/

Connected to Zabbix API Version 6.2.1
Retrieving all host groups from Zabbix...
Found 244 host groups
Found 0 existing .ini files
Loaded template from conf.d/config.ini.template
Found 244 host groups without .ini files

Created: conf.d/Valley-Rose-RV-Park-metrics.ini
Created: conf.d/Admiralty-metrics.ini
Created: conf.d/Adventure-Bound-metrics.ini
...

Summary:
Total host groups: 244
Existing .ini files: 0
Missing .ini files found: 244
Successfully created: 244
Failed to create: 0
```

## Template Customization

The script uses `conf.d/config.ini.template` as a Jinja2 template. Available template variables:

- `{{ host_group_name }}` - Original host group name
- `{{ host_group_id }}` - Zabbix host group ID
- `{{ sanitized_name }}` - Sanitized filename version

### Example Template Usage

```ini
[zabbix]
url = http://127.0.0.1:80
user = Admin
password = zabbix

# This host group: {{ host_group_name }} (ID: {{ host_group_id }})
host_groups = {{ host_group_name }}

# Add custom settings per host group if needed
# project_name = {{ sanitized_name }}_project
```

## Generated File Structure

Each generated `.ini` file contains:

```ini
[zabbix]
## zabbix info
# required
url = http://127.0.0.1:80
user = Admin
password = zabbix

# comma-separated host groups name to query for. If none specified, all host groups will be used
host_groups = Admiralty

# hosts to query for. If none specified, all hosts will be used
hosts =

# ... rest of template content ...
```

## Integration with Existing Workflow

This script is designed to work with your existing Zabbix agent deployment:

1. **Run the generator**: Creates `.ini` files for all host groups
2. **Deploy agents**: Use the generated `.ini` files to deploy individual agents
3. **Incremental updates**: Re-run the script to add `.ini` files for new host groups

## Error Handling

The script includes comprehensive error handling for:

- Zabbix connection failures
- Authentication errors
- Missing template files
- File permission issues
- Template rendering errors

## Troubleshooting

1. **Zabbix connection failed**: Check the ZABBIX_CONFIG values
2. **Template not found**: Ensure `conf.d/config.ini.template` exists
3. **Permission denied**: Check write permissions for the `conf.d` directory
4. **Template errors**: Verify Jinja2 syntax in the template file

## Security Notes

- Store credentials securely by restricting file permissions on the script
- The script disables SSL certificate verification for compatibility
- Consider using environment variables for sensitive data in production

## File Management

- The script never overwrites existing `.ini` files
- To regenerate a file, delete it first and re-run the script
- To update all files, delete the `conf.d/*.ini` files and re-run
