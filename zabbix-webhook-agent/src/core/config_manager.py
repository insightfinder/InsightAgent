"""
Configuration manager for multiple InsightFinder projects
"""
import os
import configparser
from typing import Dict, Any, Optional, List
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class InsightFinderConfig:
    """Configuration class for a single InsightFinder project"""
    
    def __init__(self, config_file: str):
        self.config_file = config_file
        self.config = configparser.ConfigParser()
        self._load_config()
    
    def _load_config(self):
        """Load configuration from INI file"""
        if not os.path.exists(self.config_file):
            raise FileNotFoundError(f"Configuration file not found: {self.config_file}")
        
        self.config.read(self.config_file)
        
        # Validate required sections
        required_sections = ['insightfinder', 'project_settings']
        for section in required_sections:
            if not self.config.has_section(section):
                raise ValueError(f"Missing required section '{section}' in {self.config_file}")
    
    @property
    def base_url(self) -> str:
        return self.config.get('insightfinder', 'base_url')
    
    @property
    def username(self) -> str:
        return self.config.get('insightfinder', 'username')
    
    @property
    def password(self) -> str:
        return self.config.get('insightfinder', 'password', fallback='')
    
    @property
    def license_key(self) -> str:
        return self.config.get('insightfinder', 'license_key')
    
    @property
    def project_name(self) -> str:
        return self.config.get('insightfinder', 'project_name')
    
    @property
    def system_name(self) -> str:
        return self.config.get('insightfinder', 'system_name')
    
    @property
    def instance_type(self) -> str:
        return self.config.get('project_settings', 'instance_type', fallback='Zabbix')
    
    @property
    def project_cloud_type(self) -> str:
        return self.config.get('project_settings', 'project_cloud_type', fallback='Zabbix')
    
    @property
    def data_type(self) -> str:
        return self.config.get('project_settings', 'data_type', fallback='Log')
    
    @property
    def insight_agent_type(self) -> str:
        return self.config.get('project_settings', 'insight_agent_type', fallback='Custom')
    
    @property
    def sampling_interval(self) -> str:
        return self.config.get('project_settings', 'sampling_interval', fallback='60')
    
    @property
    def sampling_interval_in_seconds(self) -> str:
        return self.config.get('project_settings', 'sampling_interval_in_seconds', fallback='60')
    
    @property
    def stream_resolved_alerts(self) -> bool:
        """Whether to stream resolved alerts to the API (default: True)"""
        return self.config.getboolean('project_settings', 'stream_resolved_alerts', fallback=True)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary"""
        return {
            'base_url': self.base_url,
            'username': self.username,
            'password': self.password,
            'license_key': self.license_key,
            'project_name': self.project_name,
            'system_name': self.system_name,
            'instance_type': self.instance_type,
            'project_cloud_type': self.project_cloud_type,
            'data_type': self.data_type,
            'insight_agent_type': self.insight_agent_type,
            'sampling_interval': self.sampling_interval,
            'sampling_interval_in_seconds': self.sampling_interval_in_seconds,
            'stream_resolved_alerts': self.stream_resolved_alerts
        }


class MultiProjectConfigManager:
    """Manager for multiple InsightFinder project configurations"""
    
    def __init__(self, config_dir: str = "config/insightfinder"):
        self.config_dir = Path(config_dir)
        self.configs: Dict[str, InsightFinderConfig] = {}
        self.default_config_name = "default"
        self._load_all_configs()
    
    def _load_all_configs(self):
        """Load all configuration files from the config directory"""
        if not self.config_dir.exists():
            logger.warning(f"Configuration directory does not exist: {self.config_dir}")
            return
        
        for config_file in self.config_dir.glob("*.ini"):
            config_name = config_file.stem
            try:
                self.configs[config_name] = InsightFinderConfig(str(config_file))
                logger.info(f"Loaded InsightFinder config: {config_name}")
            except Exception as e:
                logger.error(f"Failed to load config {config_file}: {e}")
    
    def get_config(self, config_name: Optional[str] = None) -> InsightFinderConfig:
        """Get configuration by name, defaults to 'default'"""
        if config_name is None:
            config_name = self.default_config_name
        
        if config_name not in self.configs:
            available_configs = list(self.configs.keys())
            raise ValueError(
                f"Configuration '{config_name}' not found. Available configs: {available_configs}"
            )
        
        return self.configs[config_name]
    
    def list_configs(self) -> List[str]:
        """List all available configuration names"""
        return list(self.configs.keys())
    
    def has_config(self, config_name: str) -> bool:
        """Check if a configuration exists"""
        return config_name in self.configs
    
    def reload_configs(self):
        """Reload all configurations"""
        self.configs.clear()
        self._load_all_configs()
    
    def get_config_summary(self) -> Dict[str, Dict[str, str]]:
        """Get summary of all configurations"""
        summary = {}
        for name, config in self.configs.items():
            summary[name] = {
                'project_name': config.project_name,
                'base_url': config.base_url,
                'username': config.username,
                'system_name': config.system_name
            }
        return summary


# Global configuration manager instance
config_manager = MultiProjectConfigManager()
