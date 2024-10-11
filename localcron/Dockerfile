FROM bitnami/python:3.12

RUN pip install requests

COPY local-cron.py .

USER 1001

ENTRYPOINT  [ "python3", "local-cron.py" ]
