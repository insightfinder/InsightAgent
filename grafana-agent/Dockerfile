FROM golang:1.23 AS builder
WORKDIR /app
COPY . .
RUN go build .

FROM debian:stable-slim
WORKDIR /app
RUN apt-get update -y && apt-get upgrade -y && apt-get install ca-certificates -y && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* && \
    useradd -m -s /bin/bash default && \
    chown -R default:default /app

ENV GRAFANA_AGENT_INTERVAL=60 \
    GRAFANA_AGENT_PATH=/app/grafana-agent

COPY --from=builder --chown=default:default /app/grafana-agent /app
COPY --chown=default:default ./config.yaml ./start.sh /app/

USER default
ENTRYPOINT ["bash","/app/start.sh"]