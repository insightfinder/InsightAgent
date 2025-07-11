"""
Data models for the Zabbix Webhook Agent
"""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel
from datetime import datetime


class ZabbixAlert(BaseModel):
    """Model for Zabbix webhook alert data"""
    alert_subject: Optional[str] = None
    alert_message: Optional[str] = None
    event_id: Optional[str] = None
    event_name: Optional[str] = None
    event_severity: Optional[str] = None
    event_status: Optional[str] = None
    event_value: Optional[str] = None
    event_date: Optional[str] = None
    event_time: Optional[str] = None
    host_name: Optional[str] = None
    host_ip: Optional[str] = None
    hostgroup_name: Optional[str] = None
    item_name: Optional[str] = None
    item_value: Optional[str] = None
    trigger_id: Optional[str] = None
    trigger_name: Optional[str] = None
    trigger_status: Optional[str] = None
    timestamp: Optional[str] = None
    raw_data: Optional[Dict[str, Any]] = None
    recovery_time: Optional[str] = None
    recovery_date: Optional[str] = None


class InsightFinderMetric(BaseModel):
    """Model for InsightFinder metric data"""
    timestamp: int
    data: Dict[str, Any]


class WebhookResponse(BaseModel):
    """Standard webhook response model"""
    status: str
    message: str
    processed_at: datetime
    data_sent: bool = False


class HealthResponse(BaseModel):
    """Health check response model"""
    status: str
    timestamp: datetime
    version: str = "1.0.0"
