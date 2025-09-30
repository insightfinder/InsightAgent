FROM golang:1.21 AS builder

WORKDIR /app

# Copy go mod files
COPY go.mod go.sum ./

# Download dependencies
RUN go mod download

# Copy source code
COPY . .

# Build the application
RUN CGO_ENABLED=0 GOOS=linux go build -a -installsuffix cgo -o loki-agent .

# Final stage
FROM alpine:latest

# Install ca-certificates for HTTPS requests
RUN apk --no-cache add ca-certificates tzdata

WORKDIR /app

# Copy the binary from builder
COPY --from=builder /app/loki-agent .

# Copy configuration directory
COPY --from=builder /app/configs ./configs

# Create non-root user
RUN adduser -D -s /bin/sh loki-agent

# Create state directory
RUN mkdir -p state && chown loki-agent:loki-agent state

# Switch to non-root user
USER loki-agent

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD pgrep loki-agent || exit 1

# Default command
CMD ["./loki-agent"]