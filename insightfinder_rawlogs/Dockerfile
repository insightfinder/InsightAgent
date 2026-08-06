FROM python:3.13-slim
ENV TZ=UTC
# no .pyc writes, so the image works with a read-only root filesystem
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
WORKDIR /app

# procps provides pgrep, used by the Helm chart's liveness/readiness probes
RUN apt-get update && apt-get install -y --no-install-recommends procps && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY rawlogs_agent.py cron.py /app/

RUN chmod +x rawlogs_agent.py cron.py && \
    mkdir -p /app/logs && \
    chown -R 10001:10001 /app

USER 10001

# Default: run on a schedule driven by config.yaml's collection.interval_seconds.
# For a one-off backfill, override the command, e.g.:
#   docker run ... python rawlogs_agent.py --replay-start ... --replay-end ...
CMD ["python", "cron.py"]
