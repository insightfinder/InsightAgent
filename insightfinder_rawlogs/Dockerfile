FROM python:3.13-slim
ENV TZ=UTC
WORKDIR /app

COPY . /app

RUN pip install --no-cache-dir -r requirements.txt && \
    chmod +x rawlogs_agent.py cron.py && \
    chown -R 1001:1001 ./

USER 1001

# Default: run on a schedule driven by config.yaml's collection.interval_seconds.
# For a one-off backfill, override the command, e.g.:
#   docker run ... python rawlogs_agent.py --replay-start ... --replay-end ...
CMD ["python", "cron.py"]
