# InsightFinder sink for statsite

## Configuration Example
Create an ini file as shown in the example below and give it as an option in the stream_command.
```ini
[insightfinder]
username = user
project_name = statsite
license_key = c123439662ad1edf64e99e97e4b776112345678
sampling_interval = 10
url = https://app.insightfinder.com
```


## How to enable
Copy insightfinder.py to your <statsite_home>/sinks folder. Add it to your statsite config files. e.g.

    stream_command = python sinks/insightfinder.py insightfinder.ini INFO 3
    
The InsightFinder sink takes an INI format configuration file as a first argument , log level as a second argument and no. of re-connect attempts as the third argument.
