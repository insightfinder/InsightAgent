# Use an official Python runtime as a parent image
FROM python:3.6-buster
ENV TZ=UTC
SHELL ["/bin/bash", "-c"]
WORKDIR /elasticsearch_collector
COPY . /elasticsearch_collector/

# Install system dependencies
RUN apt-get update && \
    apt-get install -y tzdata && \
    python3 -m venv ./venv && \
    ./venv/bin/pip install -r requirements.txt && \
    mkdir -p /elasticsearch_collector/logs && \
    touch /elasticsearch_collector/logs/cron.log

# Run the script when config.ini is provided as a volume
CMD ["/bin/bash", "-c", "source ./venv/bin/activate && nohup python3 cron.py -g 1 -o 10 -p 4 >> /elasticsearch_collector/logs/cron.log 2>&1 & tail -f /elasticsearch_collector/logs/cron.log"]
