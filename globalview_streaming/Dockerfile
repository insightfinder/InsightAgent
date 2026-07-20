FROM python:3.13-slim
ENV TZ=UTC
SHELL ["/bin/bash", "-c"]

WORKDIR /app

COPY requirements.txt /app/
RUN python3 -m pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . /app

RUN chmod +x send_gv_data.py cron.py && \
    chown -R 10001:10001 /app

USER 10001

# conf.d is provided at runtime (configMap volume). cron.py schedules the agent
# per config file at each config's run_interval.
CMD ["python3", "cron.py", "-g", "1", "-o", "10"]
