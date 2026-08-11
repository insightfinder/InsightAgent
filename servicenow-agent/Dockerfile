FROM python:3.13
ENV TZ=UTC
SHELL ["/bin/bash", "-c"]

WORKDIR /app

COPY . /app


RUN apt-get update -y && apt-get upgrade -y && \
    python3 -m pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    mkdir -p ./cache && \
    chown -R 1001:1001 ./

RUN chmod +x getmessages_servicenow.py

USER 1001

# Run the script when config.ini is provided as a volume.
# Mount conf.d read-only and a writable volume at /app/cache for the OAuth
# token cache and per-query cursors.
CMD ["/bin/bash", "-c", "python3 cron.py -g 1 -o 10 -p 4"]
