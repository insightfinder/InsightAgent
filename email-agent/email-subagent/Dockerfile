FROM python:3.11-slim

RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy shared library into the working dir so `from shared.xxx import` resolves
COPY shared/ /app/shared/

COPY email-subagent/pyproject.toml .
RUN pip install --no-cache-dir -e .

COPY email-subagent/src/ src/

EXPOSE 8008

# Run both the API server and the Temporal worker
CMD ["sh", "-c", "uvicorn src.main:app --host 0.0.0.0 --port 8008 & python -m src.worker"]
