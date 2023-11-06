FROM golang:1.21 AS builder
WORKDIR /app
COPY . /app/
RUN go mod download && go build
FROM registry.access.redhat.com/ubi9/ubi:latest
RUN dnf update -y && \
    dnf install -y ca-certificates cronie && \
    dnf clean all

WORKDIR /app
COPY --from=builder /app/loki-audit-log /app/
COPY --from=builder /app/entrypoint.sh /app/
RUN mkdir /app/conf.d && \
    chmod +x /app/loki-audit-log && \
    useradd -u 1001 -r -g 0 -d /app \
        -c "Default Application User" default && \
    chown -R 1001:0 /app && \
    echo "* * * * * cd /app && ./loki-audit-log >> /var/log/cron.log 2>&1" > /etc/cron.d/loki-audit-log && \
    echo "" >> /etc/cron.d/loki-audit-log && \
    chmod 0644 /etc/cron.d/loki-audit-log && \
    crontab /etc/cron.d/loki-audit-log && \
    touch /var/log/cron.log

CMD bash /app/entrypoint.sh