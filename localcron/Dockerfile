FROM oraclelinux:8

RUN yum install -y python2-requests

RUN mkdir -p /opt/app/

COPY local-cron.py /opt/app/

WORKDIR /opt/app/
USER 1001

ENTRYPOINT  [ "python2", "local-cron.py" ]
