# Use the slim Python 3.6.8 image as a parent image
FROM python:3.6.8-slim

# Add updated urls for debian (since this is an older image, url has updated for apt-get)
RUN echo "deb http://archive.debian.org/debian stretch main" > /etc/apt/sources.list

# Install system dependencies
RUN apt-get update && \ 
    apt-get install -y tzdata

# Set the timezone to the desired value
ENV TZ=UTC

# Install pip3
RUN apt-get install -y python3-pip

# Copy agent package
COPY elasticsearch_collector.tar.gz /

# Extract the package in the root directory
RUN tar -xzf /elasticsearch_collector.tar.gz -C /

# Set the working directory
WORKDIR /elasticsearch_collector

# Create logs directory
RUN mkdir -p /elasticsearch_collector/logs
RUN touch /elasticsearch_collector/logs/cron.log

# Configure venv and python dependencies
RUN chmod +x /elasticsearch_collector/setup/configure_python.sh && \
    ./setup/configure_python.sh

# Set the config file as a volume
VOLUME /elasticsearch_collector/conf.d/config.ini

# Run the script when config.ini is provided as a volume
CMD ["/bin/sh", "-c", " . venv/bin/activate && nohup /elasticsearch_collector/venv/bin/python3 cron.py >> /elasticsearch_collector/logs/cron.log 2>&1 & tail -f /elasticsearch_collector/logs/cron.log"]
