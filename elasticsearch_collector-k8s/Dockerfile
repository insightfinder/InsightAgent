FROM python:3.13-alpine
ENV TZ=UTC

WORKDIR /app

COPY . /app


RUN apk update && apk upgrade --no-cache && \
    python3 -m pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    python3 -m pip uninstall -y pip setuptools wheel 2>/dev/null || true && \
    rm -rf /usr/local/lib/python3.13/site-packages/pip \
           /usr/local/lib/python3.13/site-packages/pip-*.dist-info \
           /usr/local/lib/python3.13/site-packages/setuptools \
           /usr/local/lib/python3.13/site-packages/setuptools-*.dist-info \
           /usr/local/lib/python3.13/site-packages/pkg_resources \
           /usr/local/bin/pip /usr/local/bin/pip3 /usr/local/bin/pip3.13 && \
    chown -R 1001:1001 ./

# CVE-2026-119371..119379 / CVE-2026-119591: sqlite-libs 3.53.4-r0 is the latest in Alpine 3.24,
# fixed in 3.54.0. Pull only sqlite-libs from edge (musl stays on 3.24); drop once 3.24 ships it.
RUN echo '@edge https://dl-cdn.alpinelinux.org/alpine/edge/main' >> /etc/apk/repositories && \
    apk add --no-cache 'sqlite-libs@edge>=3.54' && \
    sed -i '/^@edge /d' /etc/apk/repositories && sed -i '/@edge/d' /etc/apk/world

RUN chmod +x leader_election_wrapper.py
RUN chmod +x getmessages_elasticsearch_collector.py

USER 1001

CMD ["python3", "leader_election_wrapper.py"]
