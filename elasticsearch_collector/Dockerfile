FROM python:3.13
ENV TZ=UTC
SHELL ["/bin/bash", "-c"]

WORKDIR /app

COPY . /app


RUN apt-get update -y && apt-get upgrade -y && \
    python3 -m pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    chown -R 1001:1001 ./

RUN chmod +x getmessages_elasticsearch_collector.py

USER 1001

# Run the script when config.ini is provided as a volume
CMD ["/bin/bash", "-c", "python3 cron.py -g 1 -o 10 -p 4"]