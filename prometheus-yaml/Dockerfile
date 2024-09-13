FROM python:3.8-bookworm

WORKDIR /app/prometheus

COPY agent.txt cron.py getmessages_prometheus.py requirements.txt ./
COPY conf.d/ conf.d/
COPY cache/ logs/ ./

RUN apt-get update && apt-get upgrade -y && \
    python3 -m pip install --upgrade pip && python3 -m pip install --upgrade setuptools && \
    pip3 install -r requirements.txt && pip3 install pytz && \
    groupadd --gid 10001 prometheus-agent && \
    useradd -u 10001 -g prometheus-agent prometheus-agent && \
    chown -R 10001:10001 /app

USER 10001

CMD echo "Starting..." \
    && touch logs/output.log \
    && (nohup python3 cron.py &) \
    && tail -f logs/output.log
