FROM golang:1.21 AS builder
WORKDIR /app
COPY . /app/
RUN go mod download && go build
FROM registry.access.redhat.com/ubi9/ubi:latest
RUN dnf update -y && \
    dnf install -y ca-certificates && \
    dnf clean all

WORKDIR /app
COPY --from=builder /app/kubernetes-agent /app/
RUN mkdir /app/conf.d && \
    mkdir /app/storage && \
    chmod +x /app/kubernetes-agent && \
    useradd -u 1001 -r -g 0 -d /app \
        -c "Default Application User" default && \
    chown -R 1001:0 /app
USER 1001
CMD ["/app/kubernetes-agent"]