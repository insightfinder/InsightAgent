FROM python:3.12-slim

# Set environment variables to avoid interactive prompts
ENV DEBIAN_FRONTEND=noninteractive \
    TZ=UTC \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install huggingface_hub with CLI support and clean up in one layer
RUN pip install --no-cache-dir "huggingface_hub[cli]" && \
    # Remove pip cache
    rm -rf /root/.cache/pip

# Set the entrypoint to the Hugging Face CLI
ENTRYPOINT ["huggingface-cli"]
CMD ["--help"]