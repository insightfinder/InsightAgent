# Build Dell PowerCollect Agent
FROM registry.access.redhat.com/ubi8/go-toolset:1.18.10 AS builder
USER root
COPY . /powerAgent
WORKDIR /powerAgent
RUN ./build_for_linux_in_linux_env.sh && \
    rm -rf helm_chart

# Build runtime container
FROM registry.access.redhat.com/ubi8/ubi
RUN yum update -y && yum install -y openssl ca-certificates curl && rm -rf /root/*
COPY --from=builder /powerAgent /root/powerAgent
WORKDIR /root/powerAgent

# Update Dell Root CA Certificate
RUN cp -f Dell_Root_CA.pem /etc/pki/ca-trust/source/anchors/ && \
    update-ca-trust

CMD ["/root/powerAgent/entrypoint.sh"]