import yaml
from dataclasses import dataclass, field
from typing import List, Optional, Dict


# Config of prometheus section.
@dataclass(frozen=True)
class Prometheus:
    prometheus_uri: str = ""
    user: str = ""
    password: str = ""
    verify_certs: str = "False"
    ca_certs: str = ""
    client_cert: str = ""
    client_key: str = ""
    thread_pool: str = "20"
    processes: str = ""
    timeout: str = ""
    agent_http_proxy: str = ""
    agent_https_proxy: str = ""


# Config of insightfinder section.
@dataclass(frozen=True)
class Insightfinder:
    user_name: str = ""
    license_key: str = ""
    token: str = ""
    sampling_interval: str = "5"
    run_interval: str = "5"
    chunk_size_kb: str = "2048"
    if_url: str = ""
    if_http_proxy: str = ""
    if_https_proxy: str = ""


# Config of each project.
@dataclass(frozen=True)
class Project:
    system_name: str = ""
    project_type: str = "metric"
    containerize: str = "NO"
    dynamic_metric_type: str = ""
    prometheus_query: str = ""
    prometheus_query_metric_batch_size: str = "0"
    batch_metric_filter_regex: str = ""
    prometheus_query_json: str = ""
    metrics_name_field: str = ""
    his_time_range: str = ""
    data_format: str = "json"
    timestamp_format: str = ""
    timezone: str = "UTC"
    timestamp_field: str = "timestamp"
    target_timestamp_timezone: str = "UTC"
    component_field: str = ""
    default_component_name: str = ""
    instance_field: str = ""
    instance_name_suffix: str = ""
    dynamic_host_field: str = ""
    instance_whitelist: str = ""
    device_field: str = ""
    instance_connector: str = "-"


# Total config.
@dataclass
class Config:
    prometheus: Optional[Prometheus] = None
    insightfinder: Optional[Insightfinder] = None
    projects: Dict[str, Project] = field(default_factory=dict)

    def load_yaml(self, file: str) -> bool:
        try:
            with open(file) as f:
                data = yaml.safe_load(f)
                self.prometheus = Prometheus(**data["prometheus"])
                self.insightfinder = Insightfinder(**data["insightfinder"])
                self.projects = {k: Project(**v) for k, v in data["projects"].items()}
            return True
        except Exception:
            return False


if __name__ == "__main__":
    config = Config()
    config.load_yaml("conf.d/config.yaml")
    print(config)
