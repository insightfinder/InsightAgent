FROM registry.access.redhat.com/ubi8/python-38 as builder
COPY . /opt/app-root/src/
USER root
RUN cd /opt/app-root/src && rm -rf  offline \
                                    setup \
                                    vCenter.tar.gz \
                                    Dockerfile
FROM registry.access.redhat.com/ubi8/python-38
COPY --from=builder /opt/app-root/src /opt/app-root/src
USER root
RUN dnf update -y && \
    dnf clean all
USER default
WORKDIR /opt/app-root/src
RUN pip install -r requirements.txt
CMD ["bash","entrypoint.sh"]