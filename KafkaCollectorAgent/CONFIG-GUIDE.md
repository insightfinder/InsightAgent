# Log Streaming Configuration Guide (Fixed Project Routing)

This guide walks through every field needed to configure the Kafka Collector Agent to
stream JSON log records from a single Kafka topic into **one fixed InsightFinder
project/system** — i.e. every message on the topic goes to the same place, with the
instance and (optionally) component name pulled out of each record.

This is a different routing style from the "multi-project" mode described in the main
[README.md](README.md), where the target project is derived per-message from a
`projectList` mapping. Use this guide when you have a single, dedicated Kafka topic per
logical log stream and want all of it in one InsightFinder project.

All examples below use synthetic field names and placeholder values — replace them with
your own.

---

## 1. Prerequisites

- A running Kafka cluster (or broker) reachable from wherever you run the agent, with the
  topic you want to consume already created (or auto-create enabled on the broker).
- An InsightFinder account with:
  - a **user name**
  - a **license key**
  - a target **project name** and **system name** (the project is auto-created on first
    send if it doesn't already exist)
- The built agent jar (`mvn clean package`, see main README) or the prebuilt jar in this
  repo.

---

## 2. Sample raw log record

The agent expects each Kafka message to be a single JSON object. A synthetic example:

```json
{
  "event_time": "2026-09-20T08:15:30.123Z",
  "host": "web-server-01.example.com",
  "service": "api-gateway",
  "level": "ERROR",
  "message": "Downstream request timed out after 5000ms",
  "trace_id": "b3c1a2e4-9f7d-4a1b-8c2e-1234567890ab",
  "response_time_ms": 482,
  "status_code": 500
}
```

We'll use `event_time` as the timestamp field and `host` as the instance field
throughout this guide. Substitute whatever field names your own JSON payload actually
uses.

---

## 3. Full example config

Save this as e.g. `config.properties` and fill in the placeholders (anything wrapped in
`<...>`):

```properties
# ---------------------------- Kafka consumer -------------------------------
kafka1.bootstrap.servers=<broker-host>:9092
#kafka1.security.protocol=
kafka1.group.id=<unique-consumer-group-id>
kafka1.topic=<your-kafka-topic>
kafka1.concurrency=1
kafka1.auto.offset.reset=earliest
kafka1.enable.auto.commit=true
kafka1.max.poll.interval.ms=300000
kafka1.max.poll.records=500

# ------------------------- InsightFinder connection -------------------------
insight-finder.userName=<your-insightfinder-username>
insight-finder.serverUrl=https://app.insightfinder.com
insight-finder.serverUri=/api/v1/customprojectrawdata
insight-finder.checkAndCreateUri=/api/v1/check-and-add-custom-project
insight-finder.licenseKey=<your-license-key>
insight-finder.samplingIntervalInSeconds=300
insight-finder.agentType=LogStreaming
insight-finder.dataFormat=JSON

insight-finder.bufferingTime=30
insight-finder.logMetadataBufferingTime=300
insight-finder.logParsingInfo=true
insight-finder.logSendingData=true
insight-finder.kafkaMetricLogInterval=60
insight-finder.fastRecovery=false

# ------------------------------ Log project ---------------------------------
insight-finder.logProject=true
insight-finder.vendor=<fixed-project-routing-mode>

insight-finder.logTimestampFormat=yyyy-MM-dd'T'HH:mm:ss.SSSXXX
insight-finder.logTimestampTimezone=UTC
insight-finder.logTimestampFieldPathList=event_time
insight-finder.logInstanceFieldPathList=host
insight-finder.logComponentName=<static-component-name>
#insight-finder.logComponentFieldPathList=service

insight-finder.logProjectName=<your-project-name>
insight-finder.logSystemName=<your-system-name>
```

> **`insight-finder.vendor`** selects which built-in routing strategy the agent uses.
> The default strategy (used when this key is left unset) derives the target project
> per message from a `projectList` mapping — see the main README's "Metric streaming
> mode" / "Log streaming mode" sections. The strategy this guide covers routes every
> message to one fixed project/system instead, and is what enables the
> `logProjectName` / `logSystemName` fields below. Check the resolver implementations
> under `src/main/java/.../logic/logstreaming/resolver/` in this repo for the exact
> value to set — there's already a filled-in reference config in this repo using it.

---

## 4. Field-by-field reference

### Kafka consumer (`kafka1.*`)

Every Kafka cluster/topic you consume is declared with a numbered prefix. Add
`kafka2.*`, `kafka3.*`, etc. for additional clusters/topics if needed.

| Field | Meaning |
|---|---|
| `kafka1.bootstrap.servers` | Kafka broker address(es), `host:port`, comma-separated for multiple brokers. |
| `kafka1.security.protocol` | Security protocol (e.g. `SASL_SSL`), if your cluster requires auth/TLS. Leave commented out for a plaintext/no-auth broker. |
| `kafka1.group.id` | Kafka consumer group id. Must be unique per logical consumer — reusing an existing group id resumes from its last committed offset instead of starting fresh. |
| `kafka1.topic` | The topic to consume. |
| `kafka1.concurrency` | Number of concurrent consumer threads. Set to the number of partitions on the topic for full parallelism. |
| `kafka1.auto.offset.reset` | `earliest`, `latest`, or `none` — where a brand-new consumer group starts reading from. |
| `kafka1.enable.auto.commit` | Whether Kafka offsets are committed automatically in the background. `true` is fine for most setups. |
| `kafka1.max.poll.interval.ms` | Max time allowed between `poll()` calls before the consumer is considered dead and rebalanced. |
| `kafka1.max.poll.records` | Max number of records returned per `poll()` call. |

### InsightFinder connection (`insight-finder.*`)

| Field | Meaning |
|---|---|
| `insight-finder.userName` | Your InsightFinder account user name. |
| `insight-finder.serverUrl` | Your InsightFinder server, e.g. `https://app.insightfinder.com`. |
| `insight-finder.serverUri` | API path the log data is POSTed to. Leave as `/api/v1/customprojectrawdata`. |
| `insight-finder.checkAndCreateUri` | API path used to auto-create the project/system if it doesn't already exist. Leave as `/api/v1/check-and-add-custom-project`. |
| `insight-finder.licenseKey` | Your InsightFinder license key. Treat this as a secret — don't commit a filled-in config file to source control. |
| `insight-finder.samplingIntervalInSeconds` | The IF project's configured sampling interval, in seconds. |
| `insight-finder.agentType` | `LogStreaming` for this mode. |
| `insight-finder.dataFormat` | `JSON`, since each Kafka message is a JSON object. |
| `insight-finder.bufferingTime` | How often (seconds) buffered log data is flushed and sent to InsightFinder. |
| `insight-finder.logMetadataBufferingTime` | How often (seconds) buffered instance/component metadata is flushed and sent. Must be > 0. |
| `insight-finder.logParsingInfo` | Logs details about how each raw record is parsed — useful while you're validating field paths, noisy in steady-state production. |
| `insight-finder.logSendingData` | Logs a summary (size/status) every time data is sent to IF. |
| `insight-finder.kafkaMetricLogInterval` | How often (seconds) internal Kafka consumer metrics (lag, throughput) are logged. |
| `insight-finder.fastRecovery` | `true` = on startup, seek to the latest Kafka offset (skip any backlog). `false` = resume from the last committed offset (replay any backlog). Use `false` if you need to catch up on messages produced before the agent started. |

### Log project fields

| Field | Meaning |
|---|---|
| `insight-finder.logProject` | `true` — tells the agent this is a log project, not a metric project. |
| `insight-finder.vendor` | Selects the fixed single-project routing strategy (see the callout above). |
| `insight-finder.logTimestampFormat` | The format of your timestamp field, using Java `DateTimeFormatter` pattern syntax (e.g. `yyyy-MM-dd'T'HH:mm:ss.SSSXXX`). Not needed if your timestamp field is already an epoch value (seconds or milliseconds) — those are auto-detected regardless of this setting. |
| `insight-finder.logTimestampTimezone` | Timezone applied when the timestamp string carries no explicit zone/offset. Accepts IANA names (`America/New_York`), fixed offsets (`+05:30`), or `UTC` (default). |
| `insight-finder.logTimestampFieldPathList` | JSON field path holding the timestamp (e.g. `event_time`, or a dotted path like `metadata.time` for a nested field). |
| `insight-finder.logInstanceFieldPathList` | JSON field path holding the instance name (e.g. `host`). |
| `insight-finder.logComponentName` | **Static component name applied to every record**, regardless of message content. Takes precedence over `logComponentFieldPathList` when set — this is how you pin the component to a fixed value instead of deriving it per message. |
| `insight-finder.logComponentFieldPathList` | JSON field path to derive the component name from each message (e.g. `service`). Only used when `logComponentName` is *not* set. |
| `insight-finder.logProjectName` | The fixed InsightFinder project every message is sent to. |
| `insight-finder.logSystemName` | The fixed InsightFinder system every message is sent to. |

---

## 5. How to set up

1. **Build the jar** (from the repo root):
   ```bash
   ./mvnw -q -DskipTests clean package
   ```
2. **Copy the example config** from section 3 above into your own `config.properties`
   and fill in every `<...>` placeholder with your real values.
3. **Point the timestamp/instance/component fields at your actual JSON schema.** Turn on
   `insight-finder.logParsingInfo=true` for your first run so you can see
   `can not parse timestamp` / `can not find instance` messages in the log if your field
   paths don't match.
4. **Run it:**
   ```bash
   java -jar target/KafkaCollectorAgent-0.0.1-SNAPSHOT.jar \
     --spring.config.location=file:/path/to/config.properties
   ```
5. **Confirm delivery.** Watch the console for lines like:
   ```
   sending log data
   sending data: request id: ... code: {"success":true,"message":"Success"}
   sending metadata: ... code: [{"instanceName":"...","componentName":"..."}]
   ```
   `sending data` carries the log records; `sending metadata` carries the
   instance→component mapping (only sent if an instance was successfully extracted from
   at least one message since the last flush).
6. Once you've confirmed everything looks right, turn `logParsingInfo` back down (or
   off) for normal operation to reduce log volume.

---

## 6. Choosing a static vs. per-message component name

- If every message on this topic genuinely belongs to the same logical component
  (e.g. this topic *is* one specific service's logs), set `logComponentName` to a fixed
  string and skip `logComponentFieldPathList` entirely.
- If different messages on the same topic represent different components (e.g. a shared
  topic carrying logs from several services, distinguished by a field in the payload),
  use `logComponentFieldPathList` instead and leave `logComponentName` unset.
- Component names only affect the instance→component metadata call — they are not
  embedded in the raw log payload sent to InsightFinder.
