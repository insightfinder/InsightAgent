FROM bitnami/python:3.13

COPY agent.txt cron.py getmessages_prometheus.py requirements.txt ./
COPY conf.d conf.d

RUN apt-get update -y && apt-get upgrade -y && \
    mkdir cache logs && \
    pip install -r requirements.txt && \
    chown -R 1001:1001 ./

USER 1001

CMD echo "Starting..." \
    && touch logs/output.log \
    && (python3 cron.py &) \
    && tail -f logs/output.log
