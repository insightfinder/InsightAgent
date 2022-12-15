

### How to compile:

```
cd <repo dir>
mvn package
```

### How to run:

```
java -jar <appname>.jar --spring.config.location=file:<config file dir>
```

#### How to config:

##### Log back config:

```
logging.config=file:<File Dir>/logback.xml
```

logback.xml exmple:

```
<?xml version="1.0" encoding="UTF-8"?>
<configuration>
    <!-- All log files located in logs file of the project -->
    <property name="LOGS" value="./logs" />

    <!-- Define the console log format -->
    <appender name="Console"
              class="ch.qos.logback.core.ConsoleAppender">
        <layout class="ch.qos.logback.classic.PatternLayout">
            <Pattern>
                %d{HH:mm:ss.SSS} [%thread] %-5level %logger{36} - %msg%n
            </Pattern>
        </layout>
    </appender>

    <appender name="RollingFileByDate"
              class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>${LOGS}/kafka-agent-loggerbyate.log</file>
        <encoder
                class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
            <Pattern>%d{HH:mm:ss.SSS} [%thread] %-5level %logger{36} - %msg%n</Pattern>
        </encoder>

        <rollingPolicy
                class="ch.qos.logback.core.rolling.TimeBasedRollingPolicy">
            <!-- rollover hourly and when the file reaches 10 MegaBytes -->
            <fileNamePattern>${LOGS}/kafka-agent-loggerbydate-%d{yyyy-MM-dd}.%i.log
            </fileNamePattern>
            <timeBasedFileNamingAndTriggeringPolicy
                    class="ch.qos.logback.core.rolling.SizeAndTimeBasedFNATP">
                <maxFileSize>100MB</maxFileSize>
            </timeBasedFileNamingAndTriggeringPolicy>
        </rollingPolicy>
    </appender>

    <!-- LOG everything at error level -->
    <root level="INFO">
        <appender-ref ref="RollingFileByDate" />
        <appender-ref ref="Console" />
    </root>
</configuration>
```



##### Kafka Config:

###### Every kafka cluster start with prefix start with "kafka", end with a number. Example: kafka1, kafka2

```
#kafka1 cluster one
#bootstrap servers , provided by kafka cluster team
kafka1.bootstrap.servers=
#security.protocol, provided by kafka cluster team
kafka1.security.protocol=
# consumer group id.
kafka1.group.id=
#topic name, provided by kafka cluster team
kafka1.topic=
#consumer numbers, better set it to partition number
kafka1.concurrency=
# can set it to latest, earliest, none,
#earliest: automatically reset the offset to the earliest 
#latest: automatically reset the offset to the latest
kafka1.auto.offset.reset=
#The timeout used to detect client failures 
kafka1.session.timeout.ms=
#If true the consumer’s offset will be periodically committed in the background. Default is true
kafka1.enable.auto.commit=
#The maximum delay between invocations of poll, default is 300000 (5 minutes)
kafka1.max.poll.interval.ms
#The maximum number of records returned in a single call to poll, default is 500
kafka1.max.poll.records
```

Ref to: 

https://docs.confluent.io/platform/current/installation/configuration/consumer-configs.html



##### Insight Finder config:

```
#user name for IF
insight-finder.userName=
#IF URL, example: https://stg.insightfinder.com
insight-finder.serverUrl=
#URI, the data was sent to IF, example: /api/v1/customprojectrawdata
insight-finder.serverUri=
#AUTO CREATE IF project URI, example: /api/v1/check-and-add-custom-project
insight-finder.checkAndCreateUri=
#IF license key
insight-finder.licenseKey=
#IF project sample interval
insight-finder.samplingIntervalInSeconds=300
# the key to locate project name in dataFormatRegex
insight-finder.projectKey=project
# the key to locate instance name in dataFormatRegex
insight-finder.instanceKey=instance
# the key to locate timestamp in dataFormatRegex
insight-finder.timestampKey=timestamp
# the key to locate metric name in dataFormatRegex
insight-finder.metricKey=metric
# the key to locate metric value in dataFormatRegex
insight-finder.valueKey=value
# the delimiter to split mutiple project names, example project1|project2|project3
insight-finder.projectDelimiter=\\|
# project list is in json, example: {'100|200': {'project': 'StressTestProject2','system': 'StressTestSystem'}}
# '100|200' is the project names from raw data, 'project': 'StressTestProject2' is the project mapped to IF, 'system': 
# 'StressTestSystem' is the system mapped to IF
insight-finder.projectList={'100|200': {'project': 'StressTestProject2','system': 'StressTestSystem'}}
# instanceList from raw data
insight-finder.instanceList=server-0,server-1,server-2,server-3,server-4,server-5,server-6,server-7,server-8,server-9
# metric regex
insight-finder.metricRegex=.*
#dataFormat JSON or String, if it is string need to set dataFormatRegex
insight-finder.dataFormat=String
#raw data regex
insight-finder.dataFormatRegex=^cs\\.\\|(?<project>\\w+)\\|\\.\\w+\\.\\w+\\.\\w+\\.(?<instance>\\w+\\-\\w+)\.(?<metric>.*) (?<value>[-\\d\\.]+) (?<timestamp>\\d+)
# the agent type
insight-finder.agentType=Streaming

#IF if site need ssl config, set below ssl files
insight-finder.keystoreFile=
insight-finder.keystorePassword=
insight-finder.truststoreFile=
insight-finder.truststorePassword=

#the buffer of every period, in second
insight-finder.bufferingTime=300
#show the log for parsing raw data, if not match the dataFormatRegex, still have log printed out.
insight-finder.logParsingInfo=false
#show the log for sending data to IF, data size and status. 
insight-finder.logSendingData=true
# print a specific metric raw data
insight-finder.metricNameFilter=memory.memory.free
# print the kafka consumer metrics, in second
insight-finder.kafkaMetricLogInterval=3600
```

