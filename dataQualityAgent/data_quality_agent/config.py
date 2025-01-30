import os
import yaml 
from data_quality_agent.logger import get_logger

logger = get_logger(__name__)


def load_config(config_path: str) -> dict:

    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    
    with open(config_path, "r") as file:
        try:
            config = yaml.safe_load(file)
            return config
        except yaml.YAMLError as e:
            raise ValueError(f"Error parsing configuration file: {e}")


def get_config(config_path) -> dict:
    
    logger.info(f"Loading configuration from: {config_path}")
    return load_config(config_path)


