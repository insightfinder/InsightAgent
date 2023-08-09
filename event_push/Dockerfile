FROM registry.access.redhat.com/ubi8/python-36 as builder
COPY . /opt/app-root/src/
USER root
RUN cd /opt/app-root/src && rm -rf setup/ offline/ event_push.tar.gz

FROM registry.access.redhat.com/ubi8/python-36
COPY --from=builder /opt/app-root/src /opt/app-root/src
WORKDIR /opt/app-root/src
RUN python -m venv ./venv && \
    . ./venv/bin/activate && \
    pip install -r requirements.txt
CMD ["bash","entrypoint.sh"]