# **Data Quality Agent**

**Data Quality Agent** is a Python-based tool designed to monitor and enforce data quality standards. It allows users to configure and customize validation rules based on their specific needs.

---

## **Installation**

This project uses [Poetry](https://python-poetry.org/) for dependency management. To install the package, ensure you have Poetry installed, then run:

```sh
poetry install
```

---

## **Usage**

You can run the **Data Quality Agent** locally using the following command:

```sh
poetry run agent --config /path/to/config.yaml
```

Replace `/path/to/config.yaml` with the actual path to your configuration file.

---

## **Configuration**

Everything in **Data Quality Agent** is configurable to match your needs. A sample configuration file is available at:

```
data_quality_agent/config/config.yaml.template
```

Copy this template and modify it based on your data quality requirements.

---


## **Building and Running with Docker**

### **1. Build the Docker Image**
A `Dockerfile` is provided to containerize the application. To build the Docker image, run:

```sh
docker build -t data-quality-agent .
```

### **2. Run the Container with Docker Compose**
A sample Docker Compose file is provided as `compose.yaml.template`. To run the service using Docker Compose:

1. Copy the template and rename it to `compose.yaml` and edit it according to your needs:
   ```sh
   cp compose.yaml.template compose.yaml
   ```
2. Start the service:
   ```sh
   docker compose up -d
   ```
   This will run the `data-quality-agent` container in detached mode.
   
3. You can exec into the container and run the command `agent` now


## **License**
This project is licensed under the **MIT License**.
