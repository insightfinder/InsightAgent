import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
with open(BASE_DIR / "config.yaml", "r") as f:
    _yaml_config = yaml.safe_load(f) or {}

INPUT_TYPE = _yaml_config.get("input", {}).get("type")
FILE_INPUT_FOLDER = _yaml_config.get("file_input", {}).get("folder")

OUTPUT_ENDPOINT = _yaml_config.get("output", {}).get("grpc", {}).get("endpoint")
OUTPUT_GRPC_INSECURE = _yaml_config.get("output", {}).get("grpc", {}).get("insecure", True)
OUTPUT_GRPC_MAX_MESSAGE_SIZE = _yaml_config.get("output", {}).get("grpc", {}).get("max_message_size")

IF_USERNAME = os.getenv("IF_USERNAME")
IF_LICENSEKEY = os.getenv("IF_LICENSEKEY")
IF_PROJECT = os.getenv("IF_PROJECT")
