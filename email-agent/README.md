# Email Agent

A two-agent demo (Jira II-24784) that shows multi-stage AI agent tracing in
InsightFinder. A user asks for an email; a **main agent** delegates the
drafting to a separate **subagent** that makes a real Claude call; the user
confirms; the email is really sent. Every step is traced with OpenTelemetry
and shipped to InsightFinder's own trace server.

The point of the demo is the **trace**, not the email. The two agents run as
two separate Kubernetes Pods and their spans join into a single trace, so
AI-WatchTower can render it as one multi-component workflow.

## Architecture

```
  demo_cli.py                                   (your terminal)
      |  REST
      v
  +-------------------+   HTTP POST /draft   +-----------------------+
  |    main-agent     | -------------------> |    email-subagent     |
  |  Pod, port 8007   |                      |   Pod, port 8008      |
  |                   | <------------------- |                       |
  |  - takes input    |      draft text      |  - pauses 90s         |
  |  - waits for y/n  |                      |  - calls Claude Haiku |
  |  - sends by SMTP  |                      |                       |
  +-------------------+                      +-----------------------+
         |                                             |
         |  Temporal workflow + activity spans         |
         +----------------+----------------------------+
                          v
                  traceserver (OTLP gRPC 4618)
                          v
              Jaeger  +  InsightFinder UIE / AI-WatchTower
```

Each Pod runs two processes in one container - a FastAPI server and a
Temporal worker - so a single trace shows four OTel service names:
`main-agent`, `main-agent-worker`, `email-subagent`, `email-subagent-worker`.
That is four processes, not four agents.

### Why two Pods

A single process calling a local function would produce a trace that proves
nothing about distributed tracing. The cross-Pod HTTP call is what makes the
trace interesting: the `traceparent` header has to survive the hop, and both
sides' Temporal spans have to land under one trace ID.

### The deliberate 90-second pause

The real Claude call takes about 1.5 seconds, which is too short to read as
latency on a trace view. `email-subagent` therefore pauses before drafting
(`draftDelaySeconds`, default 90) so the workflow's timing is legible. The
CLI shows a matching countdown.

This is demo-only. Three timeouts are sized around it (see
[Configuration](#configuration)); raising the pause past about 4 minutes
means raising those too.

## Layout

```
email-agent/
  main-agent/          FastAPI + Temporal worker, SMTP send      (port 8007)
  email-subagent/      FastAPI + Temporal worker, Claude call    (port 8008)
  shared/              OpenTelemetry setup used by both
  scripts/demo_cli.py  Command-line driver for the whole demo
```

The Helm chart lives in the **charts** repo: `charts/email-agent`. One chart
deploys both components, because main-agent is useless without the subagent
and the two must share one trace identity.

## Prerequisites

Already running in the Stg cluster, namespace `insightfinder`:

| Dependency | Where |
| --- | --- |
| Temporal server | `temporal-stg:7233`, namespace `default` |
| Trace server | `traceserver-temporal.traceserver.svc.cluster.local:4618` |
| Jaeger (to read traces) | `jaeger-query` in namespace `traceserver`, port 16686 |

You also need an InsightFinder project of type **Workflow** (shown as
`Multi-component` on the AI Trace page). A Model-type project will accept
the data and never display it.

## Deploy

Images are built from the `email-agent/` directory as the Docker context.

```bash
cd email-agent
docker build -f main-agent/Dockerfile -t insightfinderinc/main-agent:TAG .
docker build -f email-subagent/Dockerfile -t insightfinderinc/email-subagent:TAG .
docker push insightfinderinc/main-agent:TAG
docker push insightfinderinc/email-subagent:TAG
```

### Credentials

**No credential is stored in this repository, and none should ever be added
to it.** Supply your own before deploying:

| Credential | Where to get it | Used by |
| --- | --- | --- |
| Anthropic API key | Your own key from the Anthropic Console. Do **not** commit it, paste it into a chart value, or share an existing one. | email-subagent, for the Claude call |
| SMTP username / password | The mailbox you want to send from. Gmail and most providers need an app-specific password, not the account password. | main-agent, for the real send |
| InsightFinder trace license key | The license key of the user and environment you are sending traces to. Keys differ per user **and** per environment, so a key that works on test will not work on stg. | both, to authenticate to the trace server |

Create the Secret once, substituting your own values:

```bash
kubectl create secret generic email-agent-secrets -n insightfinder --from-literal=anthropic-api-key='YOUR_ANTHROPIC_API_KEY' --from-literal=smtp-username='YOUR_SMTP_USERNAME' --from-literal=smtp-password='YOUR_SMTP_PASSWORD' --from-literal=if-trace-license-key='YOUR_TRACE_LICENSE_KEY'
```

To run a service outside Kubernetes, put the same values in an `email-agent/.env`
file instead. That path is gitignored; keep it that way.

Then install the chart from the **charts** repo:

```bash
helm upgrade --install email-agent-stg charts/email-agent -n insightfinder --set-string mainAgent.image.tag=TAG --set-string emailSubagent.image.tag=TAG --set-string temporal.address=temporal-stg:7233 --set-string tracing.otlpEndpoint=http://traceserver-temporal.traceserver.svc.cluster.local:4618 --set-string tracing.ifUser=demoUser --set-string tracing.ifSystem=test-temporal --set-string tracing.ifProject=YOUR-WORKFLOW-PROJECT
```

That creates `<release>-main` and `<release>-subagent` Deployments and
Services. main-agent's `EMAIL_SUBAGENT_URL` is rendered from the subagent's
own Service name in the same release, so the two can never be pointed at each
other wrongly.

## How to test

### 1. Reach the main agent

```bash
kubectl port-forward -n insightfinder svc/email-agent-stg-main 8007:8007
```

```bash
curl -s http://localhost:8007/health
```

Expect `{"status":"healthy"}`.

### 2. Run the demo CLI

```bash
python3 scripts/demo_cli.py --base-url http://localhost:8007
```

It asks three things, then counts down while the subagent works:

```
Recipient email: you@example.com
Email subject/title: Weekly Tracing Demo Status
What should the email body say? Tell the team the demo is live on Stg.
  Subagent drafting ...  87s remaining

--- Drafted Email ---
Subject: Weekly Tracing Demo Status

Hi,

I wanted to let you know that the demo is live on Stg.
...
---------------------

Send this email? [y/n]: y
Final result: {... 'status': 'sent' ...}
```

The subject you type is used verbatim - the model is told to reproduce it
and the workflow sends with it, so the subject never drifts.

Useful flags:

| Flag | Meaning |
| --- | --- |
| `--base-url` | Where main-agent is reachable (default `http://localhost:8007`) |
| `--delay` | Countdown length in seconds; match `draftDelaySeconds` (default 90) |

The countdown ends on the task's real status, not on the timer, so it stays
correct if the pause is retuned or drafting finishes early.

The CLI only needs `requests`. It talks to main-agent's REST API and never
to the subagent directly.

### 3. Check the trace in Jaeger

```bash
kubectl port-forward -n traceserver svc/jaeger-query 16686:16686
```

```bash
curl -s "http://localhost:16686/api/traces?service=main-agent-worker&limit=10&lookback=10m"
```

The demo's trace is the one with roughly 34 spans covering all four service
names. Its shape should be:

```
RunActivity:call_subagent_activity     ~91s   main-agent-worker
  POST                                 ~91s   main-agent-worker       <- cross-Pod hop
    POST /draft                        ~91s   email-subagent
      RunActivity:draft_email_activity ~91s   email-subagent-worker
        generate_answer                ~1.5s  email-subagent-worker   <- the real model call
RunActivity:send_email_activity        ~3s    main-agent-worker
```

If `main-agent` and `email-subagent` appear under **two different trace IDs**,
context propagation is broken - see Troubleshooting.

### 4. Confirm it reached InsightFinder

The trace server batches for 60 seconds, so wait a minute or two.

```bash
kubectl logs -n traceserver deploy/traceserver-temporal --since=10m | grep -E "Sent trace|Sent prompt"
```

Both lines must appear for your trace ID. They are gated on a successful
HTTP response from UIE, so they mean the data was accepted, not merely sent.

Then open the **AI Trace** page and filter by your owner and workflow name.

## Configuration

### main-agent

| Env var | Chart value | Default |
| --- | --- | --- |
| `MAIN_AGENT_TEMPORAL_ADDRESS` | `temporal.address` | `temporal-test-server:7233` |
| `MAIN_AGENT_TEMPORAL_TASK_QUEUE` | `temporal.taskQueue` | `main-agent-queue` |
| `EMAIL_SUBAGENT_URL` | `subagentUrl` | `http://email-subagent:8008` |
| `SMTP_HOST` / `SMTP_PORT` | `smtp.host` / `smtp.port` | `smtp.yeah.net` / `465` |
| `SMTP_USERNAME` / `SMTP_PASSWORD` | Secret `email-agent-secrets` | required |
| `OTLP_ENDPOINT` | `tracing.otlpEndpoint` | - |
| `IF_TRACE_USER` / `IF_TRACE_PROJECT` / `IF_TRACE_SYSTEM` | `tracing.*` | - |
| `IF_TRACE_LICENSE_KEY` | Secret `email-agent-secrets` | - |

`OTLP_ENDPOINT` accepts a comma-separated list; the same spans are then
exported to every endpoint, which is useful when you do not yet know which
trace server instance the UI reads.

### email-subagent

| Env var | Chart value | Default |
| --- | --- | --- |
| `EMAIL_SUBAGENT_TEMPORAL_ADDRESS` | `temporal.address` | `temporal-test-server:7233` |
| `EMAIL_SUBAGENT_TEMPORAL_TASK_QUEUE` | `temporal.taskQueue` | `email-subagent-queue` |
| `EMAIL_SUBAGENT_DRAFT_DELAY_SECONDS` | `draftDelaySeconds` | `90` |
| `EMAIL_SUBAGENT_DEFAULT_MODEL` | - | `claude-haiku-4-5-20251001` |
| `ANTHROPIC_API_KEY` | Secret `email-agent-secrets` | required |
| tracing vars | `tracing.*` | same as main-agent |

### Timeouts tied to draftDelaySeconds

Three timeouts sit in series below the pause. All are currently 5 minutes:

| Where | Setting |
| --- | --- |
| `email-subagent/src/workflows/subagent_draft_workflow.py` | activity `start_to_close_timeout` |
| `main-agent/src/workflows/main_agent_workflow.py` | `call_subagent_activity` `start_to_close_timeout` |
| `main-agent/src/activities/main_agent.py` | `httpx.AsyncClient(timeout=...)` |

## Running the tests

```bash
cd main-agent && python -m pytest tests/ -q
```

```bash
cd email-subagent && python -m pytest tests/ -q
```

The tests make no network calls; the subagent test stubs settings directly
rather than unsetting env vars, because a local `.env` can otherwise still
supply a real API key through pydantic-settings.
