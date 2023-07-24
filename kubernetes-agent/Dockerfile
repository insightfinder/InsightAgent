FROM golang:1.20.6 AS builder
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
    chmod +x /app/kubernetes-agent
CMD ["/app/kubernetes-agent"]