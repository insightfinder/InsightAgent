FROM python:3.13
ENV TZ=UTC

WORKDIR /app

COPY . /app


RUN apt-get update -y && apt-get upgrade -y && \
    python3 -m pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    chown -R 1001:1001 ./

RUN chmod +x leader_election_wrapper.py
RUN chmod +x getmessages_elasticsearch_collector.py

USER 1001

CMD ["python3", "leader_election_wrapper.py"]
