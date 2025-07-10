"""
Configuration management for the Zabbix Webhook Agent
"""
import os
from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings"""
    
    # Server settings
    api_key: str = "default_api_key"
    log_level: str = "INFO"
    
    insightfinder_base_url: str = "https://app.insightfinder.com"
    insightfinder_username: str = ""
    insightfinder_password: str = ""  # Optional password for session management
    insightfinder_license_key: str = ""
    insightfinder_project_name: str = ""
    insightfinder_system_name: str = ""
    
    class Config:
        env_file = ".env"
        case_sensitive = False


# Global settings instance
settings = Settings()

# Import the new multi-project configuration manager
from .config_manager import config_manager
