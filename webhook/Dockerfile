# Build stage
FROM golang:1.24-alpine AS builder

WORKDIR /app

# Copy go module files
COPY go.mod ./
# Copy source code
COPY *.go ./
# Copy config file
COPY config.yaml ./

# Download dependencies
RUN go mod tidy

# Build the application
RUN CGO_ENABLED=0 GOOS=linux go build -o webhook-app .

# Final stage
FROM alpine:3.19

WORKDIR /app

# Install cron and create non-root user
RUN apk add --no-cache dcron tzdata ca-certificates && \
    addgroup -g 1000 appuser && \
    adduser -u 1000 -G appuser -s /bin/sh -D appuser

# Copy the binary from builder
COPY --from=builder /app/webhook-app .
# Copy the config file
COPY --from=builder /app/config.yaml .

# Create a startup script
RUN echo '#!/bin/sh' > /app/start.sh && \
    echo 'mkdir -p /tmp/crontabs' >> /app/start.sh && \
    echo 'echo "*/10 * * * * /app/webhook-app >> /tmp/cron.log 2>&1" > /tmp/crontabs/appuser' >> /app/start.sh && \
    echo 'touch /tmp/cron.log' >> /app/start.sh && \
    echo 'chown -R appuser:appuser /tmp/crontabs /tmp/cron.log' >> /app/start.sh && \
    echo 'crond -f -d 8 -c /tmp/crontabs &' >> /app/start.sh && \
    echo 'tail -f /tmp/cron.log' >> /app/start.sh && \
    chmod +x /app/start.sh && \
    chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Set the entrypoint to the startup script
ENTRYPOINT ["/app/start.sh"]
