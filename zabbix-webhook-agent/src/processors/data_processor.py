"""
Data processing utilities for webhook data
"""
import logging
from typing import Dict, Any, Optional
from datetime import datetime
from src.core.models import ZabbixAlert

logger = logging.getLogger(__name__)


class DataProcessor:
    """Process and transform webhook data"""
    
    @staticmethod
    def process_zabbix_webhook(raw_data: Dict[str, Any]) -> ZabbixAlert:
        """
        Process raw Zabbix webhook data into structured format
        
        Args:
            raw_data: Raw webhook data from Zabbix
            
        Returns:
            ZabbixAlert: Processed and validated alert data
        """
        try:
            # Map common Zabbix webhook fields - try both uppercase and lowercase formats
            processed_data = {
                'alert_subject': raw_data.get('ALERT.SUBJECT') or raw_data.get('alert_subject'),
                'alert_message': raw_data.get('ALERT.MESSAGE') or raw_data.get('alert_message'),
                'event_id': raw_data.get('EVENT.ID') or raw_data.get('event_id'),
                'event_name': raw_data.get('EVENT.NAME') or raw_data.get('event_name'),
                'event_severity': raw_data.get('EVENT.SEVERITY') or raw_data.get('event_severity'),
                'event_status': raw_data.get('EVENT.STATUS') or raw_data.get('event_status'),
                'event_value': raw_data.get('EVENT.VALUE') or raw_data.get('event_value'),
                'event_date': raw_data.get('EVENT.DATE') or raw_data.get('event_date'),
                'event_time': raw_data.get('EVENT.TIME') or raw_data.get('event_time'),
                'event_time_original': raw_data.get('EVENT.TIME') or raw_data.get('event_time_original'),
                'event_date_original': raw_data.get('EVENT.DATE') or raw_data.get('event_date_original'),
                'host_name': raw_data.get('HOST.NAME') or raw_data.get('host_name'),
                'host_ip': raw_data.get('HOST.IP') or raw_data.get('host_ip'),
                'item_name': raw_data.get('ITEM.NAME') or raw_data.get('item_name'),
                'item_value': raw_data.get('ITEM.VALUE') or raw_data.get('item_value'),
                'trigger_id': raw_data.get('TRIGGER.ID') or raw_data.get('trigger_id'),
                'trigger_name': raw_data.get('TRIGGER.NAME') or raw_data.get('trigger_name'),
                'trigger_status': raw_data.get('TRIGGER.STATUS') or raw_data.get('trigger_status'),
                'timestamp': raw_data.get('EVENT.DATE') or raw_data.get('event_date') or raw_data.get('DATE'),
                'hostgroup_name': raw_data.get('HOSTGROUP.NAME') or raw_data.get('hostgroup_name'),
                'recovery_time': raw_data.get('RECOVERY.TIME') or raw_data.get('recovery_time'),
                'recovery_date': raw_data.get('RECOVERY.DATE') or raw_data.get('recovery_date'),
                'recovery_time_original': raw_data.get('RECOVERY.TIME') or raw_data.get('recovery_time_original'),
                'recovery_date_original': raw_data.get('RECOVERY.DATE') or raw_data.get('recovery_date_original'),
                'raw_data': raw_data
            }
            
            # Handle additional alternative field names that might be used
            if not processed_data['host_name']:
                processed_data['host_name'] = raw_data.get('hostname') or raw_data.get('host')
            
            if not processed_data['alert_message']:
                processed_data['alert_message'] = raw_data.get('message') or raw_data.get('description')
            
            # Handle timestamp combinations for Zabbix
            if not processed_data['timestamp']:
                event_date = raw_data.get('event_date')
                event_time = raw_data.get('event_time')
                if event_date and event_time:
                    processed_data['timestamp'] = f"{event_date} {event_time}"
                else:
                    processed_data['timestamp'] = event_date or event_time
            
            # Convert timestamp if needed
            if processed_data['timestamp']:
                processed_data['timestamp'] = DataProcessor._normalize_timestamp(processed_data['timestamp'])
            
            logger.info(f"Processed Zabbix alert for host: {processed_data['host_name']}")
            logger.debug(f"Processed data: {processed_data}")
            
            return ZabbixAlert(**processed_data)
            
        except Exception as e:
            logger.error(f"Error processing Zabbix webhook data: {e}")
            # Return with raw data for fallback processing
            return ZabbixAlert(raw_data=raw_data)
    
    @staticmethod
    def _normalize_timestamp(timestamp_str: str) -> str:
        """
        Normalize timestamp string to ISO format
        
        Args:
            timestamp_str: Raw timestamp string
            
        Returns:
            str: Normalized timestamp string
        """
        try:
            # Try parsing common timestamp formats
            formats = [
                '%Y-%m-%d %H:%M:%S',
                '%Y.%m.%d %H:%M:%S',
                '%d.%m.%Y %H:%M:%S',
                '%Y-%m-%dT%H:%M:%S',
                '%Y-%m-%dT%H:%M:%SZ'
            ]
            
            for fmt in formats:
                try:
                    dt = datetime.strptime(timestamp_str, fmt)
                    return dt.isoformat()
                except ValueError:
                    continue
            
            # If no format matches, return as-is
            return timestamp_str
            
        except Exception:
            return timestamp_str
    
    @staticmethod
    def validate_required_fields(alert: ZabbixAlert) -> bool:
        """
        Validate that required fields are present
        
        Args:
            alert: Processed alert data
            
        Returns:
            bool: True if valid, False otherwise
        """
        # At minimum, we need either host_name or raw_data
        if not alert.host_name and not alert.raw_data:
            logger.warning("Alert missing both host_name and raw_data")
            return False
        
        return True
    
    @staticmethod
    def enrich_alert_data(alert: ZabbixAlert) -> Dict[str, Any]:
        """
        Enrich alert data with additional processing
        
        Args:
            alert: Processed alert data
            
        Returns:
            Dict: Enriched data ready for forwarding
        """
        enriched_data = alert.dict()
        
        # Add processing metadata
        enriched_data['processed_at'] = datetime.now().isoformat()
        enriched_data['processor_version'] = '1.0.0'
        
        # Add derived fields
        if alert.event_severity:
            enriched_data['severity_level'] = DataProcessor._map_severity_level(alert.event_severity)
        
        if alert.trigger_status:
            enriched_data['is_problem'] = alert.trigger_status.lower() in ['problem', 'active', 'true']
        
        # Clean up None values
        enriched_data = {k: v for k, v in enriched_data.items() if v is not None}
        
        return enriched_data
    
    @staticmethod
    def _map_severity_level(severity: str) -> int:
        """
        Map Zabbix severity to numeric level
        
        Args:
            severity: Severity string from Zabbix
            
        Returns:
            int: Numeric severity level (0-5)
        """
        severity_map = {
            'not classified': 0,
            'information': 1,
            'warning': 2,
            'average': 3,
            'high': 4,
            'disaster': 5
        }
        
        return severity_map.get(severity.lower(), 0)
