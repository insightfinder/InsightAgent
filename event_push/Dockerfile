FROM bitnami/python:3.13
COPY . /app
WORKDIR /app
RUN pip install -r requirements.txt && \
    touch output.log
CMD ["sh", "-c", "python cron.py & tail -f output.log"]