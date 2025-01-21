FROM bitnami/python:3.12
ENV TZ=UTC
SHELL ["/bin/bash", "-c"]
COPY . .

# Install system dependencies
RUN apt-get update -y && apt-get upgrade -y && \
    pip install -r requirements.txt && \
    chown -R 1001:1001 ./

USER 1001

# Run the script when config.ini is provided as a volume
CMD ["/bin/bash", "-c", "python3 cron.py -g 1 -o 10 -p 4"]