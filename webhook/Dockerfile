# Build stage
FROM golang:1.24-alpine AS builder

WORKDIR /app

# Copy go module files
COPY . ./

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

# Copy start up script
COPY --from=builder /app/start.sh .
# Copy the binary from builder
COPY --from=builder /app/webhook-app .
# Copy the config file
COPY --from=builder /app/config.yaml .

# Create a startup script
RUN chmod +x /app/start.sh && \
    chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Set the entrypoint to the startup script
ENTRYPOINT ["/app/start.sh"]
