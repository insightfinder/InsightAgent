# Kafka Collector Agent

A Spring Boot / Spring Kafka agent that consumes messages from one or more Kafka
clusters/topics and streams them into InsightFinder as **metric** or **log** data.

It supports:

- Multiple Kafka clusters/topics consumed concurrently (`kafka1`, `kafka2`, ...).
- Two streaming modes, selected by config: **metric streaming** and **log streaming**.
- Two log-streaming "vendors" (message shapes / routing rules): **lenovo** (default) and **visa**.
- Buffered, batched delivery to the InsightFinder custom-project raw data API, with
  automatic project creation.

---

## 1. Requirements

- Java 8 (the jar is built for Java 8 / `KafkaCollectorAgent-*-JAVA8.jar`).
- Maven (or use the bundled `./mvnw` wrapper) to build from source.
- Network access to your Kafka cluster(s) and to your InsightFinder server URL.

---

## 2. Build

```bash
cd KafkaCollectorAgent
./mvnw clean package
# or, if you have Maven installed: mvn clean package
```

This produces `target/KafkaCollectorAgent-<version>.jar`. A prebuilt
`KafkaCollectorAgent-0.0.1-SNAPSHOT-JAVA8.jar` is also included in this repo.

---

## 3. Run

```bash
java -jar KafkaCollectorAgent-0.0.1-SNAPSHOT-JAVA8.jar \
  --spring.config.location=file:/path/to/your/config.properties \
  --logging.config=file:/path/to/logback.xml
```

- `--spring.config.location` points at your filled-in config file (see below).
- `--logging.config` is optional; if omitted, the bundled `logback.xml` default is used.

### Run with Docker

```bash
docker build -t kafka-collector-agent .
docker run -d \
  -v /path/to/your/config.properties:/app/config.properties \
  -v /path/to/your/logback.xml:/app/logback.xml \
  kafka-collector-agent
```

The image bakes in `config.properties` and `logback.xml` as defaults; mount your own
files over those paths (as shown above) to override them. See `Dockerfile` for the
exact entrypoint and JVM flags used.

> Note: the container defines a healthcheck against `http://localhost:8080/actuator/health`,
> but the agent starts as a non-web Spring Boot app (`WebApplicationType.NONE`), so no HTTP
> server is exposed by default. Verify/adjust the healthcheck for your deployment if you rely
> on it (e.g. an external liveness check on the process itself, or enabling a web listener).

---

## 4. Configuration format — how this differs from the Python agents

If you're used to the Python collector agents (e.g.
`elasticsearch_collector-k8s/conf.d/config.ini.template`), note that this is a **different
agent stack** with a **different config format**:

| | Python agents (e.g. elasticsearch_collector) | Kafka Collector Agent (this repo) |
|---|---|---|
| Format | INI, with an `[insightfinder]` section | Java/Spring `.properties` — flat `key=value`, no sections |
| Framework | custom Python agent runner | Spring Boot (`spring.config.location`) |
| Common keys | `user_name`, `license_key`, `project_name`, `if_url`, ... | `insight-finder.userName`, `insight-finder.licenseKey`, `insight-finder.logProjectName`/`projectList`, `insight-finder.serverUrl`, ... |
| Source-specific config | e.g. `[elasticsearch]` section | `kafka1.*`, `kafka2.*`, ... keys (no section header) |

So it's the **same conceptual fields** (account/license, target project/system, IF URL,
sampling/buffering interval), but expressed as `insight-finder.<field>=<value>` properties
instead of an INI `[insightfinder]` block, and there's no single `project_name` field for log
mode — project (and system) routing is driven by `insight-finder.projectList` (lenovo) or
`insight-finder.logProjectName` / `logSystemName` (visa). See the field-by-field tables below.

Config files are plain `.properties` passed via `--spring.config.location=file:<path>`. This
repo ships ready-to-copy templates:

| Template | Use case |
|---|---|
| `config.properties` | Metric streaming example |
| `config-metric-template.properties` | Metric streaming, blank template |
| `config-log-template.properties` | Log streaming, lenovo vendor (default), blank template |
| `config-visa-template.properties` | Log streaming, visa vendor, blank template |

Copy the template that matches your use case, fill in the blanks, and point
`--spring.config.location` at your copy.

---

## 5. Kafka consumer configuration

Every Kafka cluster/consumer block is declared with a numbered prefix — `kafka1.*`,
`kafka2.*`, `kafka3.*`, etc. Add as many as you need (e.g. one for the primary data topic,
another for a metadata topic). Any property can be commented out to fall back to the
Kafka client default.

```properties
# bootstrap servers, provided by the Kafka cluster team (host:port, comma-separated for multiple brokers)
kafka1.bootstrap.servers=localhost:9092
# security.protocol, provided by the Kafka cluster team. Omit if no protocol/auth is required
#kafka1.security.protocol=
# consumer group id — unique per logical consumer, allows multiple consumers to share a topic
kafka1.group.id=myConsumerGroup1
# topic name, provided by the Kafka cluster team
kafka1.topic=myTopic1
# number of concurrent consumer threads — normally set to the number of partitions
kafka1.concurrency=1
# latest | earliest | none
#kafka1.auto.offset.reset=
# timeout (ms) used to detect client failures
#kafka1.session.timeout.ms=
# whether offsets are committed automatically in the background (default true)
kafka1.enable.auto.commit=true
# max delay (ms) between poll() invocations, default 300000 (5 min)
kafka1.max.poll.interval.ms=300000
# max records returned per poll(), default 500
kafka1.max.poll.records=500
```

Reference for all supported consumer properties:
https://docs.confluent.io/platform/current/installation/configuration/consumer-configs.html

**Multiple clusters/topics:** simply repeat the block with the next number, e.g. `kafka2.*`
for a second topic (in log/lenovo mode this is commonly used for a metadata topic — see
`insight-finder.logMetadataTopics` below).

---

## 6. InsightFinder connection configuration (common to both modes)

```properties
# InsightFinder account user name
insight-finder.userName=
# InsightFinder license key
insight-finder.licenseKey=
# InsightFinder server URL, e.g. https://app.insightfinder.com
insight-finder.serverUrl=https://app.insightfinder.com
# API path the data is POSTed to
insight-finder.serverUri=/api/v1/customprojectrawdata
# API path used to auto-create the project/system if it doesn't exist yet
insight-finder.checkAndCreateUri=/api/v1/check-and-add-custom-project
# IF project sampling interval, in seconds
insight-finder.samplingIntervalInSeconds=300
# Streaming | LogStreaming
insight-finder.agentType=Streaming
# how often (seconds) buffered data is flushed and sent to IF
insight-finder.bufferingTime=30
# log raw-data parsing details (useful while validating field paths / regex)
insight-finder.logParsingInfo=false
# log outbound send size/status
insight-finder.logSendingData=true
# how often (seconds) Kafka consumer metrics are logged
insight-finder.kafkaMetricLogInterval=3600
# true = seek to latest offset on start; false = resume from committed offset
insight-finder.fastRecovery=true

# Optional mTLS client cert config, only if your InsightFinder endpoint requires it.
# Leave fully commented out when unused — an empty value (key=) is still treated as
# "configured" and will break SSL setup.
#insight-finder.keystoreFile=
#insight-finder.keystorePassword=
#insight-finder.truststoreFile=
#insight-finder.truststorePassword=
```

---

## 7. Metric streaming mode

Set `insight-finder.agentType=Streaming` and `insight-finder.dataFormat` to either `JSON` or
`String`.

```properties
insight-finder.agentType=Streaming
insight-finder.dataFormat=String    # or JSON

# --- only needed when dataFormat=String, to parse the raw text via a regex ---
# key names used to pull each field out of the regex named groups below
insight-finder.projectKey=project
insight-finder.instanceKey=instance
insight-finder.timestampKey=timestamp
insight-finder.metricKey=metric
insight-finder.valueKey=value
# regex with named capture groups matching the keys above, e.g.:
# ^cs\.\|(?<project>\w+)\|\.\w+\.\w+\.\w+\.(?<instance>\w+\-\w+)\.(?<metric>.*) (?<value>[-\d\.]+) (?<timestamp>\d+)
insight-finder.dataFormatRegex=
insight-finder.metricRegex=.*

# --- routing raw project names in the data to IF project(s)/system(s) ---
# delimiter used when a raw record maps to multiple project names, e.g. project1|project2
insight-finder.projectDelimiter=\|
# JSON map: raw project name(s) -> target IF project/system
# example: {'100|200': {'project': 'StressTestProject2','system': 'StressTestSystem'}}
insight-finder.projectList={'100|200': {'project': 'StressTestProject2','system': 'StressTestSystem'}}
# comma-separated list of instance names expected in the raw data
insight-finder.instanceList=server-0,server-1,server-2

# optional: print raw data for one specific metric name, for debugging
insight-finder.metricNameFilter=memory.memory.free
```

See `config-metric-template.properties` (blank) or `config.properties` (filled example) for
a complete file.

---

## 8. Log streaming mode

Set `insight-finder.agentType=LogStreaming`, `insight-finder.dataFormat=JSON`, and
`insight-finder.logProject=true`. Log mode has two vendor strategies controlled by
`insight-finder.vendor`, which determine how a message is routed to an IF project/system.

```properties
insight-finder.agentType=LogStreaming
insight-finder.dataFormat=JSON
insight-finder.logProject=true

# common field-mapping properties (both vendors)
# timestamp format in the raw message, e.g. yyyy-MM-dd'T'HH:mm:ss  or  MMM d, yyyy @ HH:mm:ss.SSS
insight-finder.logTimestampFormat=yyyy-MM-dd'T'HH:mm:ss
# timezone applied when the timestamp string has no zone/offset (IANA name, fixed offset, or UTC)
insight-finder.logTimestampTimezone=UTC
# JSON field path(s) holding the timestamp; first match wins
insight-finder.logTimestampFieldPathList=item_time
# JSON field path(s) holding the instance name; first match wins
insight-finder.logInstanceFieldPathList=item_name
# JSON field path(s) holding the component name; join multiple paths with "&" for a "-"-joined name
insight-finder.logComponentFieldPathList=item_data.DeviceCategory&item_data.DeviceName
# how often (seconds) buffered metadata is flushed — must be > 0, required even for vendors
# (like visa) that don't emit metadata
insight-finder.logMetadataBufferingTime=300
```

### 8a. `vendor=lenovo` (default)

Routes each message by looking up a message id (`dataset_id` / `dataset_name` / `item_id`)
against a configured `projectList` map — the same project-routing style as metric mode, but
keyed by log message id instead of metric project name.

```properties
insight-finder.vendor=lenovo
# JSON fields used to build the log message id matched against projectList
insight-finder.logMessageIdFieldList=dataset_id,dataset_name,item_id
# routing map: message-id key(s) -> target IF project/system
insight-finder.projectList={'dataset_name:DeviceStatus|dataset_name:NetworkEvent': {'project': 'LogBenchmark1','system': 'LogBenchmarkSys'}}
# comma-separated Kafka topic names (see kafkaN.topic) that carry metadata rather than log records
insight-finder.logMetadataTopics=metadata1
# projects whose routing key references any of these fields do NOT receive broadcast
# metadata; leave empty to broadcast metadata to all log projects
insight-finder.logMetadataExcludeFields=dataset_name
```

Metadata is typically consumed from a second Kafka topic (e.g. `kafka2.topic=metadata1`)
and broadcast to every log project not excluded by `logMetadataExcludeFields`.

See `config-log-template.properties` for a full blank template.

### 8b. `vendor=visa`

Every message goes to a single, fixed project/system — no per-message routing and no
metadata broadcast flow.

```properties
insight-finder.vendor=visa
# fixed target project and system for every message on this consumer
insight-finder.logProjectName=my-visa-project
insight-finder.logSystemName=my-visa-system
```

See `config-visa-template.properties` for a full blank template, including a real sample
timestamp format (`MMM d, yyyy @ HH:mm:ss.SSS`).

---

## 9. Logging (`logback.xml`)

Pass a custom logback config with `--logging.config=file:<path>/logback.xml`. The bundled
`logback.xml` logs to console and to a daily/size-rolling file under `./logs`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<configuration>
    <property name="LOGS" value="./logs" />

    <appender name="Console" class="ch.qos.logback.core.ConsoleAppender">
        <layout class="ch.qos.logback.classic.PatternLayout">
            <Pattern>%d{HH:mm:ss.SSS} [%thread] %-5level %logger{36} - %msg%n</Pattern>
        </layout>
    </appender>

    <appender name="RollingFileByDate" class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>${LOGS}/kafka-agent-loggerbyate.log</file>
        <encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
            <Pattern>%d{HH:mm:ss.SSS} [%thread] %-5level %logger{36} - %msg%n</Pattern>
        </encoder>
        <rollingPolicy class="ch.qos.logback.core.rolling.TimeBasedRollingPolicy">
            <fileNamePattern>${LOGS}/kafka-agent-loggerbydate-%d{yyyy-MM-dd}.%i.log</fileNamePattern>
            <timeBasedFileNamingAndTriggeringPolicy class="ch.qos.logback.core.rolling.SizeAndTimeBasedFNATP">
                <maxFileSize>100MB</maxFileSize>
            </timeBasedFileNamingAndTriggeringPolicy>
        </rollingPolicy>
    </appender>

    <root level="INFO">
        <appender-ref ref="RollingFileByDate" />
        <appender-ref ref="Console" />
    </root>
</configuration>
```

---

## 10. Testing

```bash
./mvnw test
```

Unit tests cover config parsing, buffering, project resolution (both vendors), and the
Kafka consumer manager. `test-kafka-payload.json` is a sample raw log message useful for
manually testing field-path/timestamp parsing against your config.
