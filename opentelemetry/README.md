## Getting Started

### Instructions to register a project in Insightfinder.com
- Go to the link https://app.insightfinder.com/
- Sign in with the user credentials or sign up for a new account.
- Go to Settings->System Settings and select "Add New Project" 
- Select the "Custom" project from the list and "Create Project"
- Configure: 
	- Instance Type: Private Cloud
	- Data Type: Trace
	- Agent Type: Live Streaming
	- Hot/Cold event sampling interval: 10 min (default) 
- Create Project: 
	- Project Name
	- System Name
- Note down the project name and license key which will be used for agent installation. The license key is available in "User Account Information". To go to "User Account Information", click the userid on the top right corner.

### Installation Instructions
1. Download the OpenTelemetry Agent to the target system: [For Java](https://github.com/open-telemetry/opentelemetry-java-instrumentation/releases)
1. Set Environment Variables
	1. OTEL_SERVICE_NAME = `<Project Name>#<User Name>#<License Key>`
	1. OTEL_TRACES_EXPORTER = otlp
	1. OTEL_EXPORTER_OTLP_ENDPOINT = https://app.insightfinder.com/api
	1. OTEL_EXPORTER_OTLP_PROTOCOL = http/protobuf
1. Add OpenTelemetry Agent to Application
	1. For Java: `-javaagent:<Path>/opentelemetry-javaagent.jar`
