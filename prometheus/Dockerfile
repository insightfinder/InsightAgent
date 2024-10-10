FROM bitnami/python:3.12

COPY agent.txt cron.py getmessages_prometheus.py requirements.txt ./
COPY conf.d conf.d

RUN mkdir cache logs && \
    touch logs/output.log && \
    pip install -r requirements.txt

CMD echo "Starting..." \
    && (python3 cron.py &) \
    && tail -f logs/output.log
