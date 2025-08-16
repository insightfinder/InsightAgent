FROM bitnami/python:3.13

COPY . .

RUN apt-get update -y && apt-get upgrade -y && \
    mkdir cache logs && \
    pip install --no-cache-dir -r requirements.txt && \
    chown -R 1001:1001 ./

RUN chmod +x leader_election_wrapper.py
RUN chmod +x getmessages_prometheus.py

USER 1001

CMD ["python3", "leader_election_wrapper.py"]
