FROM python:3.6
WORKDIR /app
COPY agent.txt cron.py getmessages_prometheus.py requirements.txt ./
COPY conf.d/ conf.d/
RUN python3 -m venv venv && . venv/bin/activate \
    && pip3 install -r requirements.txt && pip3 install pytz
CMD echo "Start..." \
    && touch output.log \
    && (venv/bin/python3 cron.py &) \
    && tail -f output.log
