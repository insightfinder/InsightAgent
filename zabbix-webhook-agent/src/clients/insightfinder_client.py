"""
Enhanced InsightFinder client that matches the JavaScript webhook functionality
Includes session management, project creation, and incident investigation
"""
import json
import logging
import requests
import re
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


# Global session manager cache to share sessions across client instances
_global_session_managers = {}


def get_session_manager(base_url: str, username: str, password: str) -> 'SessionManager':
    """Get or create a session manager for the given credentials"""
    cache_key = f"{base_url.rstrip('/')}#{username}"
    
    if cache_key not in _global_session_managers:
        logger.debug(f"Creating new session manager for {username}")
        _global_session_managers[cache_key] = SessionManager(base_url, username, password)
    else:
        logger.debug(f"Reusing existing session manager for {username}")
        
        # Update password in case it changed
        session_manager = _global_session_managers[cache_key]
        session_manager.password = password
    
    return _global_session_managers[cache_key]


# We'll import settings in the class to avoid circular imports
class SessionManager:
    """Manages InsightFinder sessions and authentication"""
    
    # Class-level cache for login tokens per base_url + username combination
    _token_cache = {}
    
    def __init__(self, base_url: str, username: str, password: str):
        self.base_url = base_url.rstrip('/')
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (compatible; InsightFinderClient/1.0;)'
        })
        self.cache_key = f"{self.base_url}#{self.username}"
        self.login_token = None
        
        # Try to get existing token from cache
        if self.cache_key in self._token_cache:
            cached_data = self._token_cache[self.cache_key]
            self.login_token = cached_data.get('token')
            logger.debug(f"Loaded cached token for {self.username}")
    
    def _cache_token(self, token: str):
        """Cache the login token for reuse"""
        self._token_cache[self.cache_key] = {
            'token': token,
            'timestamp': datetime.now().timestamp()
        }
        logger.debug(f"Cached token for {self.username}")
    
    def _clear_cached_token(self):
        """Clear the cached token when it's invalid"""
        if self.cache_key in self._token_cache:
            del self._token_cache[self.cache_key]
        self.login_token = None
        logger.debug(f"Cleared cached token for {self.username}")
    
    def login(self) -> str:
        """
        Login to InsightFinder and get authentication token
        Matches the JavaScript SessionManager.login function
        """
        logger.info(f"Attempting login to InsightFinder for user: {self.username}...")
        
        login_params = {
            'userName': self.username,
            'password': self.password
        }
        
        login_url = f"{self.base_url}/api/v1/login-check"
        
        try:
            response = self.session.post(
                login_url,
                params=login_params,
                headers={'Content-Type': 'application/json'},
                timeout=30
            )
            
            logger.debug(f"Login response status: {response.status_code}")
            logger.debug(f"Login response data: {response.text}")
            
            if response.status_code != 200:
                raise Exception(f"Login failed with status: {response.status_code}")
            
            login_data = response.json()
            if not login_data.get('valid'):
                raise Exception("Invalid login credentials")
            
            self.login_token = login_data.get('token')
            
            # Cache the token for reuse
            self._cache_token(self.login_token)
            
            logger.info(f"Login successful for {self.username}, token obtained and cached")
            return self.login_token
            
        except Exception as e:
            logger.error(f"Error during login for {self.username}: {e}")
            # Clear any cached token on login failure
            self._clear_cached_token()
            raise
    
    def incident_investigation(self, project_name: str, instance_name: str, 
                             timestamp: int, status: str = 'closed') -> bool:
        """
        Call incident investigation API for resolved events
        Matches the JavaScript SessionManager.incidentInvestigation function
        """
        logger.info(f"Calling incident investigation API for project: {project_name}, instance: {instance_name}")
        
        # Ensure we have a login token
        if not self.ensure_logged_in():
            logger.error("Unable to obtain login token")
            return False
        
        return self._make_incident_investigation_request(project_name, instance_name, timestamp, status)
    
    def _make_incident_investigation_request(self, project_name: str, instance_name: str, 
                                           timestamp: int, status: str) -> bool:
        """Make the actual incident investigation API request"""
        try:
            api_url = f"{self.base_url}/api/v1/incidentInvestigation"
            params = {'tzOffset': '-14400000'}
            
            form_data = {
                'projectName': project_name,
                'instanceName': instance_name,
                'timestamp': str(timestamp),
                'status': status
            }
            
            logger.debug(f"Form data being sent: {form_data}")
            
            response = self.session.post(
                api_url,
                params=params,
                data=form_data,
                headers={
                    'X-CSRF-TOKEN': self.login_token,
                    'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8'
                },
                timeout=30
            )
            
            logger.debug(f"API response status: {response.status_code}")
            logger.debug(f"API response data: {response.text}")
            
            if response.status_code == 200:
                # Parse response to check for success - incident API always returns 200
                response_text = response.text.lower()
                
                # Check if the response indicates authentication failure
                if any(auth_error in response_text for auth_error in ['unauthorized', 'invalid token', 'authentication failed', 'csrf']):
                    logger.warning("Authentication failed, token expired or invalid. Clearing cache and re-authenticating...")
                    
                    # Clear the cached token and force re-login
                    self._clear_cached_token()
                    
                    try:
                        self.login()  # Re-login with fresh token
                        # Retry the request with new token
                        return self._make_incident_investigation_request(project_name, instance_name, timestamp, status)
                    except Exception as e:
                        logger.error(f"Failed to re-authenticate: {e}")
                        return False
                
                # Check for success indicator in response (must contain 'success')
                if 'success' in response_text and 'true' in response_text:
                    logger.info("✅ Incident investigation API call was successful!")
                    return True
                elif 'success' in response_text and 'false' in response_text:
                    logger.warning("❌ API returned success=false - operation failed")
                    logger.debug(f"Response content: {response.text}")
                    return False
                elif 'success' in response_text:
                    # Contains 'success' but format is unclear, log and assume success
                    logger.info("✅ Incident investigation API call appears successful (contains 'success')")
                    return True
                else:
                    logger.warning("❌ API returned 200 but no clear success indicator - attempting to renew token and retry once")
                    logger.debug(f"Response content: {response.text}")
                    # Only retry once: add a flag to prevent infinite recursion
                    if not getattr(self, '_incident_retry', False):
                        self._clear_cached_token()
                        try:
                            self.login()
                            self._incident_retry = True
                            return self._make_incident_investigation_request(project_name, instance_name, timestamp, status)
                        except Exception as e:
                            logger.error(f"Failed to re-authenticate after ambiguous response: {e}")
                            return False
                        finally:
                            self._incident_retry = False
                    else:
                        logger.error("Already retried once, not retrying again to avoid infinite loop")
                        return False
            else:
                logger.error(f"Failed to update incident investigation. Status: {response.status_code}, Response: {response.text}")
                # Check if it's an authentication error
                if response.status_code in [401, 403]:
                    logger.info("Received authentication error, clearing cached token")
                    self._clear_cached_token()
                return False
                
        except Exception as e:
            logger.error(f"Error calling incident investigation API: {e}")
            return False
    
    def is_logged_in(self) -> bool:
        """Check if we have a valid login token"""
        return self.login_token is not None
    
    def ensure_logged_in(self) -> bool:
        """Ensure we have a valid login token, login if necessary"""
        if not self.is_logged_in():
            try:
                logger.debug(f"No cached token found for {self.username}, logging in...")
                self.login()
                return True
            except Exception as e:
                logger.error(f"Failed to login: {e}")
                return False
        else:
            logger.debug(f"Using cached token for {self.username}")
        return True


class InsightFinderClient:
    """Enhanced InsightFinder client matching JavaScript webhook functionality"""
    
    def __init__(self, config_name: Optional[str] = None, if_config: Optional[Dict[str, Any]] = None):
        """
        Initialize InsightFinder client with configuration
        
        Args:
            config_name: Name of the configuration to use from config files
            if_config: Direct configuration dictionary (overrides config_name)
        """
        if if_config:
            # Use provided configuration directly
            self.base_url = if_config['base_url'].rstrip('/')
            self.username = if_config['username']
            self.password = if_config.get('password', '')
            self.license_key = if_config['license_key']
            self.project_name = if_config['project_name']
            self.system_name = if_config.get('system_name', '')
            self.instance_type = if_config.get('instance_type', '')
            self.project_cloud_type = if_config.get('project_cloud_type', '')
            self.data_type = if_config.get('data_type', '')
            self.insight_agent_type = if_config.get('insight_agent_type', 'Custom')
            self.sampling_interval = if_config.get('sampling_interval', '60')
            self.sampling_interval_in_seconds = if_config.get('sampling_interval_in_seconds', '60')
        else:
            # Use configuration from files or fallback to legacy settings
            try:
                from src.core.config import config_manager
                if_config_obj = config_manager.get_config(config_name)
                config_dict = if_config_obj.to_dict()
                
                self.base_url = config_dict['base_url'].rstrip('/')
                self.username = config_dict['username']
                self.password = config_dict['password']
                self.license_key = config_dict['license_key']
                self.project_name = config_dict['project_name']
                self.system_name = config_dict['system_name']
                self.instance_type = config_dict['instance_type']
                self.project_cloud_type = config_dict['project_cloud_type']
                self.data_type = config_dict['data_type']
                self.insight_agent_type = config_dict['insight_agent_type']
                self.sampling_interval = config_dict['sampling_interval']
                self.sampling_interval_in_seconds = config_dict['sampling_interval_in_seconds']
            except Exception as e:
                # Fallback to legacy settings from .env
                from src.core.config import settings
                
                self.base_url = settings.insightfinder_base_url.rstrip('/')
                self.username = settings.insightfinder_username
                self.password = getattr(settings, 'insightfinder_password', '')
                self.license_key = settings.insightfinder_license_key
                self.project_name = settings.insightfinder_project_name
                self.system_name = getattr(settings, 'insightfinder_system_name', settings.insightfinder_project_name)  # Use project name as system name
                self.instance_type = 'Zabbix'
                self.project_cloud_type = 'Zabbix'
                self.data_type = 'Log'
                self.insight_agent_type = 'Custom'
                self.sampling_interval = '60'
                self.sampling_interval_in_seconds = '60'
        
        self.session = requests.Session()
        self.session_manager = None
        
        # Initialize session manager if password is provided using global cache
        if self.password:
            self.session_manager = get_session_manager(self.base_url, self.username, self.password)
    
    def make_safe_instance_string(self, instance: str, device: str = '') -> str:
        """
        Create safe instance string matching JavaScript makeSafeInstanceString function
        """
        if not instance:
            return ''
        
        # Replace underscores with dots
        instance = re.sub(r'_+', '.', instance)
        # Replace colons with hyphens
        instance = re.sub(r':+', '-', instance)
        # Remove leading special characters
        instance = re.sub(r'^[-_\W]+', '', instance)
        
        # If there's a device, concatenate it
        if device:
            device_safe = self.make_safe_instance_string(device)
            instance = f"{device_safe}_{instance}"
        
        return instance
    
    def check_and_create_project(self) -> bool:
        """
        Check if project exists and create if it doesn't
        Matches JavaScript checkAndCreateProject function
        """
        logger.info(f"Starting check project: {self.project_name}")
        
        # First check if project exists
        check_data = {
            'operation': 'check',
            'userName': self.username,
            'licenseKey': self.license_key,
            'projectName': self.project_name
        }
        
        try:
            response = self.session.post(
                f"{self.base_url}/api/v1/check-and-add-custom-project",
                data=check_data,
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
                timeout=30
            )
            
            if response.status_code != 200:
                raise Exception(f"Project check failed with status: {response.status_code}")
            
            check_result = response.json()
            if check_result.get('success') and check_result.get('isProjectExist'):
                logger.info(f"Project exists: {self.project_name}")
                return True
                
        except Exception as e:
            logger.warning(f"Failed to parse project check response: {e}")
        
        # Project doesn't exist, create it
        logger.info(f"Creating project: {self.project_name}")
        
        create_data = {
            'operation': 'create',
            'userName': self.username,
            'licenseKey': self.license_key,
            'projectName': self.project_name,
            'systemName': self.system_name,
            'instanceType': self.instance_type,
            'projectCloudType': self.project_cloud_type,
            'dataType': self.data_type,
            'insightAgentType': self.insight_agent_type,
            'samplingInterval': self.sampling_interval,
            'samplingIntervalInSeconds': self.sampling_interval_in_seconds
        }
        
        response = self.session.post(
            f"{self.base_url}/api/v1/check-and-add-custom-project",
            data=create_data,
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            timeout=30
        )
        
        if response.status_code != 200:
            raise Exception(f"Project creation failed with status: {response.status_code}")
        
        create_result = response.json()
        if create_result.get('success'):
            logger.info(f"Project created successfully: {self.project_name}")
            return True
        else:
            raise Exception(f"Project creation failed: {create_result.get('message', 'Unknown error')}")
    
    def send_log_data_enhanced(self, zabbix_data: Dict[str, Any]) -> bool:
        """
        Send log data to InsightFinder matching the JavaScript webhook format
        """
        try:
            # Check and create project if necessary
            self.check_and_create_project()
            
            # Parse timestamp from Zabbix data
            timestamp = self._parse_zabbix_timestamp(zabbix_data)
            
            # Determine event type (matches JavaScript logic)
            event_value = zabbix_data.get('event_value', '1')
            is_resolved = (event_value == '0' or event_value == 0)
            event_type = 'RESOLVED' if is_resolved else 'PROBLEM'
            
            # Create safe instance name
            raw_instance_name = zabbix_data.get('host_name', 'unknown-host')
            safe_instance_name = self.make_safe_instance_string(raw_instance_name)
            
            # Create alert message
            alert_message = self._create_alert_message(zabbix_data, event_type)
            
            zone_name = zabbix_data.get('hostgroup_name', '')
            
            # Prepare alert data in InsightFinder format (matches JavaScript)
            alert_data = {
                'timestamp': str(timestamp),
                'tag': safe_instance_name,
                'data': {
                    'message': alert_message,
                    'event_type': event_type,
                    'source': 'zabbix-webhook',
                    'event_id': zabbix_data.get('event_id'),
                    'event_name': zabbix_data.get('event_name'),
                    'event_severity': zabbix_data.get('event_severity'),
                    'event_status': zabbix_data.get('event_status'),
                    'event_value': zabbix_data.get('event_value'),
                    'host_name': zabbix_data.get('host_name'),
                    'host_ip': zabbix_data.get('host_ip'),
                    'hostgroup_name': zabbix_data.get('hostgroup_name'),
                    'item_name': zabbix_data.get('item_name'),
                    'item_value': zabbix_data.get('item_value'),
                    'trigger_id': zabbix_data.get('trigger_id'),
                    'trigger_name': zabbix_data.get('trigger_name'),
                    'trigger_status': zabbix_data.get('trigger_status'),
                    'event_date': zabbix_data.get('event_date'),
                    'event_time': zabbix_data.get('event_time'),
                },
                'componentName': safe_instance_name,
                'zoneName': zone_name,
                'ipAddress': zabbix_data.get('host_ip'),
            }

            # Prepare post data exactly like JavaScript
            post_data = {
                'userName': self.username,
                'licenseKey': self.license_key,
                'projectName': self.project_name,
                'instanceName': safe_instance_name,
                'agentType': 'LogStreaming',
                'metricData': json.dumps([alert_data])
            }
            
            logger.info(f"Sending request to: {self.base_url}/api/v1/customprojectrawdata")
            logger.info(f"Instance: {safe_instance_name}")
            logger.info(f"Alert tag: {alert_data['tag']}")
            logger.info(f"Zone name: {zone_name}")
            logger.debug(f"Full alert data: {json.dumps(alert_data, indent=2)}")
            
            response = self.session.post(
                f"{self.base_url}/api/v1/customprojectrawdata",
                data=post_data,
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
                timeout=30
            )
            
            if response.status_code != 200:
                raise Exception(f"Response code: {response.status_code}, Response: {response.text}")
            
            logger.info(f"Received response with status code {response.status_code}")
            logger.debug(f"Response: {response.text}")
            
            try:
                result = response.json()
                if result.get('success') is False:
                    raise Exception(f"InsightFinder API returned error: {result.get('message', 'Unknown error')}")
            except json.JSONDecodeError:
                # If we can't parse but got 200, assume success
                logger.info("Could not parse response but got 200 status, assuming success")
            
            logger.info(f"Successfully sent alert for host: {raw_instance_name} (safe: {safe_instance_name})")
            
            # Handle incident investigation for resolved events
            if is_resolved and self.session_manager:
                logger.info("Event is RESOLVED, calling incident investigation API...")
                logger.debug(f"Using session manager for {self.username} (cached: {self.session_manager.is_logged_in()})")
                try:
                    # Call incident investigation (it will handle login internally if needed)
                    investigation_success = self.session_manager.incident_investigation(
                        self.project_name,
                        safe_instance_name,
                        timestamp,
                        'closed'
                    )
                    
                    if investigation_success:
                        logger.info("✅ Successfully called incident investigation API")
                    else:
                        logger.warning("❌ Incident investigation API call failed")
                        
                except Exception as e:
                    logger.error(f"Error in incident investigation: {e}")
                    # Don't fail the main operation for investigation issues
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to send log data to InsightFinder: {e}")
            return False
    
    def _parse_zabbix_timestamp(self, zabbix_data: Dict[str, Any]) -> int:
        """Parse timestamp from Zabbix data"""
        event_time = zabbix_data.get('event_time')
        event_date = zabbix_data.get('event_date')
        
        if event_time and event_date:
            # Normalize date format
            normalized_date = event_date.replace('.', '-')
            datetime_str = f"{normalized_date}T{event_time}"
            
            try:
                dt = datetime.fromisoformat(datetime_str)
                return int(dt.timestamp() * 1000)  # milliseconds
            except ValueError:
                logger.warning(f"Invalid date/time format: {datetime_str}")
        
        # Fallback to current timestamp
        return int(datetime.now().timestamp() * 1000)
    
    def _create_alert_message(self, zabbix_data: Dict[str, Any], event_type: str) -> str:
        """Create comprehensive alert message"""
        alert_message = ''
        
        if zabbix_data.get('alert_subject'):
            alert_message = zabbix_data['alert_subject']
        else:
            trigger_name = zabbix_data.get('trigger_name') or zabbix_data.get('event_name', 'Unknown Event')
            alert_message = f"{event_type}: {trigger_name}"
        
        if zabbix_data.get('alert_message'):
            alert_message += f"\n{zabbix_data['alert_message']}"
        
        return alert_message
    
    def send_metric_data(self, zabbix_data: Dict[str, Any]) -> bool:
        """
        Send metric data to InsightFinder
        """
        return False # future implementation, currently not used
    
    def send_log_data(self, zabbix_data: Dict[str, Any]) -> bool:
        """
        Send log data to InsightFinder
        """
        return self.send_log_data_enhanced(zabbix_data)


def clear_all_session_cache():
    """Clear all cached session managers and tokens"""
    global _global_session_managers
    
    # Clear tokens from all session managers
    for session_manager in _global_session_managers.values():
        session_manager._clear_cached_token()
    
    # Clear the global cache
    _global_session_managers.clear()
    logger.info("Cleared all cached session managers and tokens")


def get_cached_session_info() -> Dict[str, Any]:
    """Get information about cached sessions for debugging"""
    info = {}
    for cache_key, session_manager in _global_session_managers.items():
        info[cache_key] = {
            'has_token': session_manager.is_logged_in(),
            'base_url': session_manager.base_url,
            'username': session_manager.username
        }
    return info
