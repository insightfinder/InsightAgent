# ServiceNow Ticket Creation Script

This Python project allows you to create ServiceNow incident tickets programmatically using the ServiceNow REST API.

## Features

- ✅ Create ServiceNow incident tickets via REST API
- ✅ Configuration-driven ticket creation using YAML
- ✅ Scheduled ticket creation at specific times
- ✅ Detailed error handling and logging
- ✅ Support for all incident fields (urgency, impact, category, etc.)

## Prerequisites

- Python 3.7 or higher
- ServiceNow instance access with credentials
- Internet connection to reach your ServiceNow instance

## Installation

1. Create and activate a virtual environment (recommended):
```bash
python3 -m venv venv
source venv/bin/activate  # On Linux/Mac
# or
venv\Scripts\activate  # On Windows
```

2. Install required Python packages:
```bash
pip install -r requirements.txt
```

## Configuration

Edit `config.yaml` to configure your ServiceNow instance and ticket details:

```yaml
servicenow:
  instance_url: "https://your-instance.service-now.com"
  username: "your_username"
  password: "your_password"

ticket:
  short_description: "Your ticket title"
  description: "Detailed description"
  urgency: "3"  # 1=High, 2=Medium, 3=Low
  impact: "3"   # 1=High, 2=Medium, 3=Low
  category: "inquiry"
```

## Usage

### Create Ticket Immediately

Run the script to create a ticket immediately:

```bash
python create_ticket.py
```

## Ticket Fields

You can configure the following fields in `config.yaml`:

- **short_description** (required): Brief title of the incident
- **description**: Detailed description of the incident
- **urgency**: 1 (High), 2 (Medium), 3 (Low)
- **impact**: 1 (High), 2 (Medium), 3 (Low)
- **category**: inquiry, software, hardware, network, database, etc.
- **assignment_group**: Name of the group to assign
- **assigned_to**: Username to assign the ticket to

## Output

When a ticket is created successfully, you'll see:

```
============================================================
TICKET CREATED SUCCESSFULLY
============================================================
Ticket Number: INC0010123
Sys ID: abc123def456...
Short Description: Sample incident
State: 1
Priority: 5
Created: 2026-01-09 10:30:00
============================================================

Ticket URL: https://your-instance.service-now.com/now/nav/ui/classic/params/target/incident.do?sys_id=abc123def456
```

## Troubleshooting

### Authentication Errors
- Verify your username and password in `config.yaml`
- Check if your ServiceNow instance URL is correct

### Connection Errors
- Ensure you have internet connectivity
- Verify the ServiceNow instance is accessible
- Check if there are any firewall restrictions

### Permission Errors
- Ensure your ServiceNow user has permissions to create incidents
- Contact your ServiceNow administrator if needed

## Security Note

⚠️ **Important**: The `config.yaml` file contains sensitive credentials. 

- Never commit this file to version control
- Consider using environment variables or secure credential storage
- Restrict file permissions: `chmod 600 config.yaml`

## License

This project is provided as-is for educational and business purposes.
