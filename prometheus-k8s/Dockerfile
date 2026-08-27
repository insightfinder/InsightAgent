FROM python:3.13-alpine
ENV TZ=UTC

WORKDIR /app

COPY . /app

RUN apk update && apk upgrade --no-cache && \
    python3 -m pip install --upgrade pip && \
    mkdir cache logs && \
    pip install --no-cache-dir -r requirements.txt && \
    python3 -m pip uninstall -y pip setuptools wheel 2>/dev/null || true && \
    rm -rf /usr/local/lib/python3.13/site-packages/pip \
           /usr/local/lib/python3.13/site-packages/pip-*.dist-info \
           /usr/local/lib/python3.13/site-packages/setuptools \
           /usr/local/lib/python3.13/site-packages/setuptools-*.dist-info \
           /usr/local/lib/python3.13/site-packages/pkg_resources \
           /usr/local/bin/pip /usr/local/bin/pip3 /usr/local/bin/pip3.13 && \
    chown -R 1001:1001 ./

RUN chmod +x leader_election_wrapper.py
RUN chmod +x getmessages_prometheus.py

USER 1001

CMD ["python3", "leader_election_wrapper.py"]
