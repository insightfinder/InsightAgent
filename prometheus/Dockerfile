FROM python:3.8-bookworm

WORKDIR /app

COPY agent.txt cron.py getmessages_prometheus.py requirements.txt ./
COPY conf.d/ conf.d/

RUN apt-get update && apt-get upgrade -y && \
    python3 -m pip install --upgrade pip && python3 -m pip install --upgrade setuptools && \
    pip3 install -r requirements.txt && pip3 install pytz

CMD echo "Start..." \
    && touch output.log \
    && (python3 cron.py &) \
    && tail -f output.log
