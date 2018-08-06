# InsightFinder sink for statsite

## Configuration Example
Create an ini file as shown in the example below and give it as an option in the stream_command.
```ini
[insightfinder]
username = <insightfinder_username>
project_name = <insightfinder_project_name>
license_key = <insightfinder_license_key>
sampling_interval = <statsite_flushing_interval>
url = <insightfinder_app_url>
filter_string = <string_to_filter_metric_keys> (optional)
```
**Options:**
```
- username:  Insightfinder application user-name. You can get it from this page: https://app.insightfinder.com/account-info
- project_name: InsightFinder project to send data to
- license_key: InsightFinder license key. You can get it from this page: https://app.insightfinder.com/account-info
- sampling_interval: statsite sampling interval in seconds
- url (optional) : Host url to send data to. Its https://app.insightfinder.com by default
- host_range: point index of host start to host end, Its 2,4 by default
- metric_name_range: point index of metric start to metric end(end is till the metric key end by default), Its 4 by default
```

## How to enable
Copy insightfinder.py to your <statsite_home>/sinks folder. Add it to your statsite config files. e.g.

    stream_command = python sinks/insightfinder.py insightfinder.ini INFO 1 3000
    
The InsightFinder sink takes an INI format configuration file as a first argument , log level as a second argument, no. of re-connect attempts as the third argument and packet size as the last argument.
