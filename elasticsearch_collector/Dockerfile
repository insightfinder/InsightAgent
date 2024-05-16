# Use an official Python runtime as a parent image
FROM python:3.8-bookworm
ENV TZ=UTC
SHELL ["/bin/bash", "-c"]
WORKDIR /elasticsearch_collector
COPY . /elasticsearch_collector/

# Install system dependencies
RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y tzdata && \
    python3 -m pip install --upgrade pip && python3 -m pip install --upgrade setuptools && \
    python3 -m pip install -r requirements.txt && \
    groupadd --gid 10001 es-agent && \
    useradd -u 10001 -g es-agent es-agent && \
    chown -R 10001:10001 /elasticsearch_collector

USER 10001

# Run the script when config.ini is provided as a volume
CMD ["/bin/bash", "-c", "python3 cron.py -g 1 -o 10 -p 4"]