# Use an official Python runtime as a parent image
FROM python:3.6-buster

# Install system dependencies
RUN apt-get update && \
    apt-get install -y tzdata

# Set the timezone to the desired value
ENV TZ=UTC

# Copy agent package
COPY elasticsearch_collector.tar.gz /

# Extract the package in the root directory
RUN tar -xzf /elasticsearch_collector.tar.gz -C /

# Set the working directory
WORKDIR /elasticsearch_collector

# Configure logs and setup python
RUN mkdir -p /elasticsearch_collector/logs && \
    touch /elasticsearch_collector/logs/cron.log && \
    pip3 install -r requirements.txt --no-index --find-links=./offline/pip/packages/

# Set the config file as a volume
VOLUME /elasticsearch_collector/conf.d/config.ini

# Run the script when config.ini is provided as a volume
CMD ["/bin/sh", "-c", "nohup python3 cron.py -g 1 -o 10 -p 4 >> /elasticsearch_collector/logs/cron.log 2>&1 & tail -f /elasticsearch_collector/logs/cron.log"]
