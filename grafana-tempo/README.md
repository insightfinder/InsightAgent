# Grafana Tempo Agent

Streams trace data from Grafana Tempo to InsightFinder.

Tempo is a trace store and does not push data out, so the agent polls it:

1. Every `agent.interval` it searches Tempo (`GET /api/search`) with a TraceQL query for the
   traces in the last window. The window is closed `agent.delay` ago, so spans that arrive late
   are already in Tempo.
2. For each new trace ID it fetches the full trace (`GET /api/traces/<id>`,
   `Accept: application/protobuf`). Tempo returns it as OpenTelemetry (OTLP) protobuf, whatever
   protocol the trace was originally sent with (OTLP, Jaeger or Zipkin).
3. It sends the trace unchanged, as an OTLP gRPC export, to the InsightFinder trace server
   (OpenTelemetryService-Trace), with the `ifuser`, `iflicensekey`, `ifproject` and `ifsystem`
   headers. The trace server creates the trace project if needed and sends the trace to
   InsightFinder.

If a search returns `tempo.limit` traces, the window is split in half and searched again, so a
busy window is not cut short. Trace IDs already sent are skipped. The end of the last processed
window is written to `agent.state_file`, so a restart continues where it stopped.

## Build

```shell
go build -o grafana-tempo-agent .
```

Cross-compile for Linux from Windows:

```powershell
$env:GOOS="linux"; $env:GOARCH="amd64"; $env:CGO_ENABLED="0"; go build -o grafana-tempo-agent .
```

## Run

```shell
cp config.yaml.example config.yaml
./grafana-tempo-agent -c config.yaml
```

See `config.yaml.example` for every option. Useful ones:

| Option | Meaning |
|---|---|
| `tempo.endpoint` | Tempo HTTP API, e.g. `http://tempo:3200` |
| `tempo.tenant_id` | Sent as `X-Scope-OrgID` for multi-tenant Tempo |
| `tempo.username` / `tempo.password` | Basic auth, e.g. Grafana Cloud Traces |
| `tempo.query` | TraceQL selecting the traces to stream, default `{}` (all) |
| `insightfinder.trace_server` | Trace server OTLP gRPC address, `host:port` |
| `insightfinder.dry_run` | `true` fetches from Tempo and logs, sends nothing |
| `agent.start_time` / `agent.end_time` | RFC3339 range for a backfill |

## Demo with fake data

`demo/tempo-local.yaml` runs a single-binary Tempo with local storage, listening on
`127.0.0.1` only. `tools/fakegen` sends fake OTLP traces to it: a checkout flow across
`frontend`, `checkout-service`, `inventory-service`, `orders-db` and `payment-service`, with
some failed payments and some slow database queries.

```shell
# 1. Tempo (download tempo_<version>_linux_amd64.tar.gz from the Tempo GitHub releases)
./tempo -target=all -config.file=demo/tempo-local.yaml

# 2. Fake traces: 5 traces every 10s, 10% failed payments, 10% slow DB queries
go run ./tools/fakegen -endpoint http://localhost:4318 -n 5 -interval 10s

# 3. Agent: dry run first, then set dry_run: false and the InsightFinder settings
./grafana-tempo-agent -c config.yaml
```
