"""
Utility functions for the Zabbix Webhook Agent
"""
import json
import logging
from typing import Dict, Any, List
from datetime import datetime

logger = logging.getLogger(__name__)


class LoggerUtils:
    """Utility functions for logging and debugging"""
    
    @staticmethod
    def log_webhook_data(data: Dict[str, Any], prefix: str = "Webhook"):
        """
        Log webhook data in a structured format
        
        Args:
            data: Data to log
            prefix: Log message prefix
        """
        logger.info(f"{prefix} data received:")
        logger.info(f"  Host: {data.get('host_name', 'unknown')}")
        logger.info(f"  Event: {data.get('event_name', 'unknown')}")
        logger.info(f"  Severity: {data.get('event_severity', 'unknown')}")
        logger.info(f"  Status: {data.get('event_status', 'unknown')}")
        
        # Log full data at debug level
        logger.debug(f"{prefix} full data: {json.dumps(data, indent=2)}")


class DataValidation:
    """Data validation utilities"""
    
    @staticmethod
    def validate_insightfinder_config() -> bool:
        """
        Validate InsightFinder configuration
        
        Returns:
            bool: True if configuration is valid
        """
        from src.core.config import settings
        
        required_fields = [
            'insightfinder_username',
            'insightfinder_license_key',
            'insightfinder_project_name'
        ]
        
        for field in required_fields:
            if not getattr(settings, field, None):
                logger.error(f"Missing required InsightFinder configuration: {field}")
                return False
        
        return True


class MetricsCollector:
    """Collect and track server metrics"""
    
    def __init__(self):
        self.stats = {
            'webhooks_received': 0,
            'webhooks_processed': 0,
            'data_sent_to_insightfinder': 0,
            'errors': 0,
            'start_time': datetime.now().isoformat()
        }
    
    def increment_webhook_received(self):
        """Increment webhook received counter"""
        self.stats['webhooks_received'] += 1
    
    def increment_webhook_processed(self):
        """Increment webhook processed counter"""
        self.stats['webhooks_processed'] += 1
    
    def increment_data_sent(self):
        """Increment data sent counter"""
        self.stats['data_sent_to_insightfinder'] += 1
    
    def increment_errors(self):
        """Increment error counter"""
        self.stats['errors'] += 1
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get current statistics
        
        Returns:
            Dict: Current server statistics
        """
        uptime = datetime.now() - datetime.fromisoformat(self.stats['start_time'])
        
        return {
            **self.stats,
            'uptime_seconds': uptime.total_seconds(),
            'current_time': datetime.now().isoformat()
        }


# Global metrics collector instance
metrics_collector = MetricsCollector()
