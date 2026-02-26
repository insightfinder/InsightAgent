#!/usr/bin/env python3
"""
Price Scenario Simulator for Data Quality Agent

This script simulates various price-related data quality scenarios:
1. source price valid, target price missing
2. source price valid, target price NA
3. source price missing, target price NA
   - price1 has data, price2 has data
   - price1 does not have data, price2 has data
   - price1 and price2 don't have data
4. source price missing, target price missing
   - price1 has data, price2 has data
   - price1 does not have data, price2 has data
   - price1 and price2 don't have data
5. negative price in target
   - price1 has data, price2 has data
   - price1 does not have data, price2 has data
   - price1 and price2 don't have data
6. no target
7. no issue (source and target prices are equal - perfect match)

All scenarios are configurable via class variables at the top of this script.

InsightFinder Integration:
--------------------------
The script can send generated logs directly to InsightFinder for analysis.
Configure the following variables to enable InsightFinder integration:
- SEND_TO_INSIGHTFINDER: Set to True to enable sending data
- IF_USER_NAME: Your InsightFinder username
- IF_LICENSE_KEY: Your InsightFinder license key
- IF_PROJECT_NAME: Project name in InsightFinder (will be created if doesn't exist)
- IF_URL: InsightFinder URL (default: https://app.insightfinder.com)
- WRITE_TO_FILES: Set to False if you only want to send to InsightFinder (no local files)
"""

import json
import re
from datetime import datetime
import random
import urllib.parse
import requests
import socket
import logging
import yaml
import os
from typing import Dict, List, Any, Optional

# ============================================================================
# CONFIGURATION - MODIFY THESE VALUES TO CONFIGURE SCENARIOS
# ============================================================================

# Path to configuration file
CONFIG_PATH = "./config.yaml"

# Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
LOG_LEVEL = "INFO"

# ============================================================================
# LOGGING AND CONFIG HELPER FUNCTIONS
# ============================================================================

LOG_FORMAT = "%(asctime)s [%(levelname)s] (%(name)s): %(message)s"

def setup_logging(level: str):
    """Set up logging configuration."""
    logging.basicConfig(level=level, format=LOG_FORMAT)

def get_logger(name: str):
    """Get a logger with the specified name."""
    return logging.getLogger(name)

def load_config(config_path: str) -> dict:
    """Load YAML configuration from file."""
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    
    with open(config_path, "r") as file:
        try:
            config = yaml.safe_load(file)
            return config
        except yaml.YAMLError as e:
            raise ValueError(f"Error parsing configuration file: {e}")

def get_config(config_path: str) -> dict:
    """Load and return configuration."""
    logger = get_logger(__name__)
    logger.info(f"Loading configuration from: {config_path}")
    return load_config(config_path)

# ============================================================================
# SCENARIO CONFIGURATION
# ============================================================================

# Scenario 1: source price valid, target price missing
NUM_SOURCE_VALID_TARGET_MISSING = 2

# Scenario 2: source price valid, target price NA
NUM_SOURCE_VALID_TARGET_NA = 2

# Scenario 3: source price missing, target price NA
NUM_SOURCE_MISSING_TARGET_NA_P1_P2_BOTH = 1        # price1 and price2 both have data
NUM_SOURCE_MISSING_TARGET_NA_P1_EMPTY_P2_DATA = 1  # price1 empty, price2 has data
NUM_SOURCE_MISSING_TARGET_NA_BOTH_EMPTY = 1        # both price1 and price2 empty

# Scenario 4: source price missing, target price missing
NUM_SOURCE_MISSING_TARGET_MISSING_P1_P2_BOTH = 1        # price1 and price2 both have data
NUM_SOURCE_MISSING_TARGET_MISSING_P1_EMPTY_P2_DATA = 1  # price1 empty, price2 has data
NUM_SOURCE_MISSING_TARGET_MISSING_BOTH_EMPTY = 1        # both price1 and price2 empty

# Scenario 5: negative price in target
NUM_NEGATIVE_PRICE_P1_P2_BOTH = 1        # price1 and price2 both have data
NUM_NEGATIVE_PRICE_P1_EMPTY_P2_DATA = 1  # price1 empty, price2 has data
NUM_NEGATIVE_PRICE_BOTH_EMPTY = 1        # both price1 and price2 empty

# Scenario 6: no target (unmatched)
NUM_NO_TARGET = 2

# Scenario 7: no issue (source and target price are equal, perfect match)
NUM_NO_ISSUE = 35

# Inconsistency configuration
# Comma-separated list of target fields that can be made inconsistent
# For scenarios 1-5, one random field from this list will be prefixed with 'INCONSISTENT_'
# Leave empty string "" to disable this feature
INCONSISTENT_FIELDS = "orderType,transactionId,multiplier"

# Price range configuration
MIN_PRICE = 99.0    # Minimum price value
MAX_PRICE = 101.0    # Maximum price value

# Timestamp range for data generation
# Logs are always generated for the last 10 minutes from current time
# Set to None to use this default behavior
# You can override by setting specific times: "YYYY-MM-DD HH:MM:SS" or epoch seconds (int)
START_TIME = None  # Will be set to (current_time - 10 minutes)
END_TIME = None    # Will be set to current_time

# ============================================================================
# INSIGHTFINDER CONFIGURATION
# ============================================================================

# Enable/disable sending data to InsightFinder
SEND_TO_INSIGHTFINDER = True

# InsightFinder credentials
IF_USER_NAME = ""  # Your InsightFinder username
IF_LICENSE_KEY = ""  # Your InsightFinder license key
IF_PROJECT_NAME = ""  # Project name in InsightFinder
IF_URL = "https://stg.insightfinder.com"  # InsightFinder URL

# Still write to log files?
WRITE_TO_FILES = True  # Set to False to only send to InsightFinder

# ============================================================================
# END OF CONFIGURATION
# ============================================================================

HOSTNAME = socket.gethostname().partition('.')[0]
SESSION = requests.Session()

# ============================================================================
# INSIGHTFINDER HELPER FUNCTIONS
# ============================================================================

def send_data_to_insightfinder(logger, log_data_list, record_type):
    """Send log data to InsightFinder."""
    if not SEND_TO_INSIGHTFINDER:
        logger.info("InsightFinder sending is disabled")
        return True
    
    if not IF_USER_NAME or not IF_LICENSE_KEY:
        logger.error("InsightFinder credentials not configured. Please set IF_USER_NAME and IF_LICENSE_KEY")
        return False
    
    if not log_data_list:
        logger.info(f"No {record_type} records to send to InsightFinder")
        return True
    
    try:
        # Prepare data in InsightFinder format
        post_data = {
            'userName': IF_USER_NAME,
            'licenseKey': IF_LICENSE_KEY,
            'projectName': IF_PROJECT_NAME,
            'instanceName': HOSTNAME,
            'agentType': 'LogStreaming',
            'metricData': json.dumps(log_data_list)
        }
        
        # Post to InsightFinder API
        post_url = urllib.parse.urljoin(IF_URL, '/api/v1/customprojectrawdata')
        
        logger.info(f'Sending {len(log_data_list)} {record_type} records to InsightFinder...')
        logger.debug(f'Post URL: {post_url}')
        logger.debug(f'First record: {log_data_list[0] if log_data_list else "None"}')
        logger.debug(f'Last record: {log_data_list[-1] if log_data_list else "None"}')
        
        response = SESSION.post(
            post_url,
            data=post_data,
            verify=False,
            timeout=60
        )
        
        if response.status_code == 200:
            logger.info(f'Successfully sent {len(log_data_list)} {record_type} records to InsightFinder')
            return True
        else:
            logger.error(f'Failed to send data to InsightFinder. Status code: {response.status_code}')
            logger.error(f'Response: {response.text}')
            return False
            
    except Exception as e:
        logger.error(f'Error sending data to InsightFinder: {e}')
        import traceback
        logger.debug(traceback.format_exc())
        return False


def check_and_create_project(logger):
    """Check if project exists in InsightFinder, create if not."""
    if not SEND_TO_INSIGHTFINDER:
        return True
    
    if not IF_USER_NAME or not IF_LICENSE_KEY:
        logger.warning("InsightFinder credentials not configured. Skipping project check.")
        return False
    
    try:
        # Check if project exists
        logger.info(f'Checking if project exists: {IF_PROJECT_NAME}')
        params = {
            'operation': 'check',
            'userName': IF_USER_NAME,
            'licenseKey': IF_LICENSE_KEY,
            'projectName': IF_PROJECT_NAME,
        }
        url = urllib.parse.urljoin(IF_URL, 'api/v1/check-and-add-custom-project')
        response = SESSION.post(url, data=params, verify=False, timeout=10)
        
        if response.status_code != 200:
            logger.error(f'Failed to check project. Status code: {response.status_code}')
            return False
        
        result = response.json()
        if result.get('success') and result.get('isProjectExist'):
            logger.info(f'Project {IF_PROJECT_NAME} already exists')
            return True
        
        # Create project if it doesn't exist
        logger.info(f'Creating project: {IF_PROJECT_NAME}')
        params = {
            'operation': 'create',
            'userName': IF_USER_NAME,
            'licenseKey': IF_LICENSE_KEY,
            'projectName': IF_PROJECT_NAME,
            'systemName': IF_PROJECT_NAME,
            'instanceType': 'PrivateCloud',
            'projectCloudType': 'PrivateCloud',
            'dataType': 'Log',
            'insightAgentType': 'Custom',
            'samplingInterval': 10,  # 10 minutes
            'samplingIntervalInSeconds': 600,
        }
        
        response = SESSION.post(url, data=params, verify=False, timeout=10)
        
        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
                logger.info(f'Successfully created project: {IF_PROJECT_NAME}')
                return True
            else:
                logger.error(f'Failed to create project: {result}')
                return False
        else:
            logger.error(f'Failed to create project. Status code: {response.status_code}')
            return False
            
    except Exception as e:
        logger.error(f'Error checking/creating project: {e}')
        import traceback
        logger.debug(traceback.format_exc())
        return False


def parse_time_string(time_str: str) -> int:
    """Parse a time string to epoch seconds.
    
    Supports formats:
    - YYYY-MM-DD HH:MM:SS
    - Epoch seconds (as string or int)
    """
    if not time_str:
        return None
        
    # Try parsing as epoch seconds first
    try:
        return int(float(time_str))
    except ValueError:
        pass
    
    # Try parsing as datetime string
    try:
        dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
        return int(dt.timestamp())
    except ValueError:
        raise ValueError(f"Invalid time format: {time_str}. Use 'YYYY-MM-DD HH:MM:SS' or epoch seconds")


class PriceScenarioSimulator:
    """Simulates various price-related data quality scenarios."""
    
    def __init__(self, config_path: str):
        """Initialize simulator with configuration."""
        self.config = get_config(config_path)
        self.logger = get_logger(__name__)
        
        # Get the first mapping configuration
        self.mapping_config = list(self.config['mappings'].values())[0]
        self.source = self.mapping_config['source']
        self.target = self.mapping_config['target']
        
        # Extract configuration details
        self.id_columns = self.mapping_config['id_columns']
        self.consistency_check_columns = self.mapping_config['consistency_check_columns']
        self.extra_columns_to_fill = self.mapping_config['extra_columns_to_fill']
        self.timestamp_config = self.mapping_config['timestamp']
        
        # Validate INCONSISTENT_FIELDS configuration
        self._validate_inconsistent_fields()
        
        # Load transformation rules from config
        self.transformation_rules = self._load_rules_from_config()
        self.consistency_rules = self._load_consistency_rules_from_config()
        
        # Set up timestamp range
        current_time = int(datetime.now().timestamp())
        
        # Parse start and end times from global configuration
        if START_TIME is not None:
            if isinstance(START_TIME, str):
                self.start_time = parse_time_string(START_TIME)
            else:
                self.start_time = START_TIME
        else:
            # Default: last 10 minutes
            self.start_time = current_time - 600  # 600 seconds = 10 minutes
        
        if END_TIME is not None:
            if isinstance(END_TIME, str):
                self.end_time = parse_time_string(END_TIME)
            else:
                self.end_time = END_TIME
        else:
            # Default: current time
            self.end_time = current_time
        
        if self.start_time >= self.end_time:
            raise ValueError("Start time must be before end time")
        
        # Calculate total records needed
        self.total_records = self._calculate_total_records()
        
        # Convert timestamps to readable format for logging
        start_readable = datetime.fromtimestamp(self.start_time).strftime('%Y-%m-%d %H:%M:%S')
        end_readable = datetime.fromtimestamp(self.end_time).strftime('%Y-%m-%d %H:%M:%S')
        
        self.logger.info(f"Initialized price scenario simulator for {self.source} -> {self.target} mapping")
        self.logger.info(f"Timestamp range: {start_readable} to {end_readable}")
        self.logger.info(f"Total records to generate: {self.total_records}")

    def _validate_inconsistent_fields(self):
        """Validate that all fields in INCONSISTENT_FIELDS are also in consistency_check_columns."""
        if not INCONSISTENT_FIELDS or not INCONSISTENT_FIELDS.strip():
            return  # No validation needed if INCONSISTENT_FIELDS is empty
        
        inconsistent_field_list = [f.strip() for f in INCONSISTENT_FIELDS.split(',') if f.strip()]
        
        # Check each field
        invalid_fields = []
        for field in inconsistent_field_list:
            if field not in self.consistency_check_columns:
                invalid_fields.append(field)
        
        if invalid_fields:
            error_msg = (
                f"Invalid INCONSISTENT_FIELDS configuration: The following fields are not in "
                f"consistency_check_columns from config.yaml: {', '.join(invalid_fields)}\n"
                f"consistency_check_columns in config: {', '.join(self.consistency_check_columns)}\n"
                f"Please update INCONSISTENT_FIELDS to only include fields from consistency_check_columns."
            )
            raise ValueError(error_msg)
        
        self.logger.info(f"Validated INCONSISTENT_FIELDS: All {len(inconsistent_field_list)} field(s) are in consistency_check_columns")

    def _calculate_total_records(self) -> int:
        """Calculate total number of records needed based on global configuration."""
        return (
            NUM_SOURCE_VALID_TARGET_MISSING +
            NUM_SOURCE_VALID_TARGET_NA +
            NUM_SOURCE_MISSING_TARGET_NA_P1_P2_BOTH +
            NUM_SOURCE_MISSING_TARGET_NA_P1_EMPTY_P2_DATA +
            NUM_SOURCE_MISSING_TARGET_NA_BOTH_EMPTY +
            NUM_SOURCE_MISSING_TARGET_MISSING_P1_P2_BOTH +
            NUM_SOURCE_MISSING_TARGET_MISSING_P1_EMPTY_P2_DATA +
            NUM_SOURCE_MISSING_TARGET_MISSING_BOTH_EMPTY +
            NUM_NEGATIVE_PRICE_P1_P2_BOTH +
            NUM_NEGATIVE_PRICE_P1_EMPTY_P2_DATA +
            NUM_NEGATIVE_PRICE_BOTH_EMPTY +
            NUM_NO_TARGET +
            NUM_NO_ISSUE
        )

    def _load_rules_from_config(self) -> Dict[str, Any]:
        """Load and compile all transformation rules from config."""
        rules = {}
        
        for col, rule_code in self.mapping_config['rules'].items():
            try:
                rule_namespace = {'logger': self.logger}
                exec(rule_code, rule_namespace)
                rules[col] = rule_namespace[col + 'Rule']
            except Exception as e:
                self.logger.error(f"Error loading rule for {col}: {e}")
                rules[col] = lambda row: ""
        
        return rules

    def _load_consistency_rules_from_config(self) -> Dict[str, Any]:
        """Load and compile all consistency check rules from config."""
        rules = {}
        
        for col in self.consistency_check_columns:
            try:
                if col in self.mapping_config.get('consistency_check_rules', {}):
                    rule_code = self.mapping_config['consistency_check_rules'][col]
                else:
                    rule_code = self.mapping_config['rules'][col]
                
                rule_namespace = {'logger': self.logger}
                exec(rule_code, rule_namespace)
                rules[col] = rule_namespace[col + 'Rule']
            except Exception as e:
                self.logger.error(f"Error loading consistency rule for {col}: {e}")
                rules[col] = lambda row: ""
        
        return rules

    def generate_base_record(self, record_id: int) -> Dict[str, Any]:
        """Generate a base record with standard fields."""
        instruments = ['EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'XAUUSD', 'XAGUSD']
        event_types = ['NEW', 'CONFIRMED', 'CANCELLED', 'REJECTED', 'TRADE']
        order_types = ['QUOTED', 'MARKET', 'LIMIT']
        directions = ['BUY', 'SELL']
        instrument_types = ['SPOT', 'SWAP', 'BLOCK', 'OUTRIGHT', 'ABC']
        
        tradeCurrencies = random.choice(instruments)
        
        # Compute currentOrder based on tradeCurrencies
        curr_order = ''
        if len(tradeCurrencies) >= 6:
            if ord(tradeCurrencies[:1]) < ord(tradeCurrencies[3:4]):
                curr_order = 'left'
            elif ord(tradeCurrencies[:1]) > ord(tradeCurrencies[3:4]):
                curr_order = 'right'
            else:
                if ord(tradeCurrencies[1:2]) < ord(tradeCurrencies[4:5]):
                    curr_order = 'left'
                elif ord(tradeCurrencies[1:2]) > ord(tradeCurrencies[4:5]):
                    curr_order = 'right'
                else:
                    if ord(tradeCurrencies[2:3]) < ord(tradeCurrencies[5:6]):
                        curr_order = 'left'
                    elif ord(tradeCurrencies[2:3]) > ord(tradeCurrencies[5:6]):
                        curr_order = 'right'
                    else:
                        curr_order = 'equal'
        else:
            curr_order = 'left'
        
        record = {
            'orderId': f'ORD{1000 + record_id}',
            'l_id': str(random.randint(0, 3)),
            'allocationId': f'ALLOC{record_id}',
            'q_id': f'QUOTE{record_id}',
            'instType': random.choice(instrument_types),
            'transactionType': random.choice(event_types),
            'orderType': random.choice(order_types),
            'direction': random.choice(directions),
            'tradeCurrencies': tradeCurrencies,
            'datetime_epoch': str(random.randint(self.start_time, self.end_time)),
            'allocationQty': str(random.randint(1000, 10000)),
            'q_unit': random.choice(['BASE', 'COUNTER']),
            'directionMatchesRequest': random.choice(['true', 'false']),
            'block_l_direction': random.choice(['BUY', 'SELL']),
            'mCode': random.choice(['XLON', 'XNYS', 'XXXX', '']),
            'tenor': random.choice(['SPOT', '1M', '3M']),
            'currentOrder': curr_order,
            'id': str(record_id)
        }
        
        return record

    def generate_synthetic_source_data(self) -> List[Dict[str, Any]]:
        """Generate synthetic source data based on global scenario configuration."""
        source_data = []
        record_id = 0
        
        # Track scenario assignments for each record
        scenario_map = {}
        
        # Scenario 1: source valid, target missing
        for i in range(NUM_SOURCE_VALID_TARGET_MISSING):
            record = self.generate_base_record(record_id)
            record['price'] = str(round(random.uniform(MIN_PRICE, MAX_PRICE), 4))
            record['price1'] = str(round(random.uniform(MIN_PRICE, MAX_PRICE), 4))
            record['price2'] = str(round(random.uniform(MIN_PRICE, MAX_PRICE), 4))
            source_data.append(record)
            scenario_map[record_id] = ('source_valid_target_missing', {})
            record_id += 1
        
        # Scenario 2: source valid, target NA
        for i in range(NUM_SOURCE_VALID_TARGET_NA):
            record = self.generate_base_record(record_id)
            record['price'] = str(round(random.uniform(MIN_PRICE, MAX_PRICE), 4))
            record['price1'] = str(round(random.uniform(MIN_PRICE, MAX_PRICE), 4))
            record['price2'] = str(round(random.uniform(MIN_PRICE, MAX_PRICE), 4))
            source_data.append(record)
            scenario_map[record_id] = ('source_valid_target_na', {})
            record_id += 1
        
        # Scenario 3: source missing, target NA (3 sub-scenarios)
        for i in range(NUM_SOURCE_MISSING_TARGET_NA_P1_P2_BOTH):
            record = self.generate_base_record(record_id)
            record['price'] = ""
            record['price1'] = str(round(random.uniform(MIN_PRICE, MAX_PRICE), 4))
            record['price2'] = str(round(random.uniform(MIN_PRICE, MAX_PRICE), 4))
            source_data.append(record)
            scenario_map[record_id] = ('source_missing_target_na', {'price1': 'data', 'price2': 'data'})
            record_id += 1
        
        for i in range(NUM_SOURCE_MISSING_TARGET_NA_P1_EMPTY_P2_DATA):
            record = self.generate_base_record(record_id)
            record['price'] = ""
            record['price1'] = ""
            record['price2'] = str(round(random.uniform(MIN_PRICE, MAX_PRICE), 4))
            source_data.append(record)
            scenario_map[record_id] = ('source_missing_target_na', {'price1': 'empty', 'price2': 'data'})
            record_id += 1
        
        for i in range(NUM_SOURCE_MISSING_TARGET_NA_BOTH_EMPTY):
            record = self.generate_base_record(record_id)
            record['price'] = ""
            record['price1'] = ""
            record['price2'] = ""
            source_data.append(record)
            scenario_map[record_id] = ('source_missing_target_na', {'price1': 'empty', 'price2': 'empty'})
            record_id += 1
        
        # Scenario 4: source missing, target missing (3 sub-scenarios)
        for i in range(NUM_SOURCE_MISSING_TARGET_MISSING_P1_P2_BOTH):
            record = self.generate_base_record(record_id)
            record['price'] = ""
            record['price1'] = str(round(random.uniform(MIN_PRICE, MAX_PRICE), 4))
            record['price2'] = str(round(random.uniform(MIN_PRICE, MAX_PRICE), 4))
            source_data.append(record)
            scenario_map[record_id] = ('source_missing_target_missing', {'price1': 'data', 'price2': 'data'})
            record_id += 1
        
        for i in range(NUM_SOURCE_MISSING_TARGET_MISSING_P1_EMPTY_P2_DATA):
            record = self.generate_base_record(record_id)
            record['price'] = ""
            record['price1'] = ""
            record['price2'] = str(round(random.uniform(MIN_PRICE, MAX_PRICE), 4))
            source_data.append(record)
            scenario_map[record_id] = ('source_missing_target_missing', {'price1': 'empty', 'price2': 'data'})
            record_id += 1
        
        for i in range(NUM_SOURCE_MISSING_TARGET_MISSING_BOTH_EMPTY):
            record = self.generate_base_record(record_id)
            record['price'] = ""
            record['price1'] = ""
            record['price2'] = ""
            source_data.append(record)
            scenario_map[record_id] = ('source_missing_target_missing', {'price1': 'empty', 'price2': 'empty'})
            record_id += 1
        
        # Scenario 5: negative price in target (3 sub-scenarios)
        for i in range(NUM_NEGATIVE_PRICE_P1_P2_BOTH):
            record = self.generate_base_record(record_id)
            record['price'] = str(round(random.uniform(MIN_PRICE, MAX_PRICE), 4))
            record['price1'] = str(round(random.uniform(MIN_PRICE, MAX_PRICE), 4))
            record['price2'] = str(round(random.uniform(MIN_PRICE, MAX_PRICE), 4))
            source_data.append(record)
            scenario_map[record_id] = ('negative_price', {'price1': 'data', 'price2': 'data'})
            record_id += 1
        
        for i in range(NUM_NEGATIVE_PRICE_P1_EMPTY_P2_DATA):
            record = self.generate_base_record(record_id)
            record['price'] = str(round(random.uniform(MIN_PRICE, MAX_PRICE), 4))
            record['price1'] = ""
            record['price2'] = str(round(random.uniform(MIN_PRICE, MAX_PRICE), 4))
            source_data.append(record)
            scenario_map[record_id] = ('negative_price', {'price1': 'empty', 'price2': 'data'})
            record_id += 1
        
        for i in range(NUM_NEGATIVE_PRICE_BOTH_EMPTY):
            record = self.generate_base_record(record_id)
            record['price'] = str(round(random.uniform(MIN_PRICE, MAX_PRICE), 4))
            record['price1'] = ""
            record['price2'] = ""
            source_data.append(record)
            scenario_map[record_id] = ('negative_price', {'price1': 'empty', 'price2': 'empty'})
            record_id += 1
        
        # Scenario 6: no target
        for i in range(NUM_NO_TARGET):
            record = self.generate_base_record(record_id)
            record['price'] = str(round(random.uniform(MIN_PRICE, MAX_PRICE), 4))
            record['price1'] = str(round(random.uniform(MIN_PRICE, MAX_PRICE), 4))
            record['price2'] = str(round(random.uniform(MIN_PRICE, MAX_PRICE), 4))
            source_data.append(record)
            scenario_map[record_id] = ('no_target', {})
            record_id += 1
        
        # Scenario 7: no issue (source and target price are equal)
        for i in range(NUM_NO_ISSUE):
            record = self.generate_base_record(record_id)
            record['price'] = str(round(random.uniform(MIN_PRICE, MAX_PRICE), 4))
            record['price1'] = str(round(random.uniform(MIN_PRICE, MAX_PRICE), 4))
            record['price2'] = str(round(random.uniform(MIN_PRICE, MAX_PRICE), 4))
            source_data.append(record)
            scenario_map[record_id] = ('no_issue', {})
            record_id += 1
        
        self.scenario_map = scenario_map
        self.logger.info(f"Generated {len(source_data)} synthetic source records")
        return source_data

    def generate_synthetic_target_data(self, source_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Generate synthetic target data based on scenario configuration."""
        target_data = []
        
        # Parse inconsistent fields configuration
        inconsistent_field_list = []
        if INCONSISTENT_FIELDS and INCONSISTENT_FIELDS.strip():
            inconsistent_field_list = [f.strip() for f in INCONSISTENT_FIELDS.split(',') if f.strip()]
        
        for idx, source_record in enumerate(source_data):
            record_id = int(source_record['id'])
            
            # Skip records in 'no_target' scenario
            if self.scenario_map[record_id][0] == 'no_target':
                continue
            
            # Generate target record using transformation rules
            target_record = {'id': str(idx)}
            # target_record = {'id': str(record_id)}
            
            # Apply transformation rules
            for col in self.id_columns + self.extra_columns_to_fill:
                if col in self.transformation_rules:
                    try:
                        computed_value = self.transformation_rules[col](source_record)
                        target_record[col] = computed_value
                    except Exception as e:
                        self.logger.debug(f"Error applying rule for {col}: {e}")
                        target_record[col] = ""
                else:
                    target_record[col] = source_record.get(col, "")
            
            # Apply scenario-specific price modifications
            scenario_type, scenario_details = self.scenario_map[record_id]
            
            if scenario_type == 'source_valid_target_missing':
                target_record['price'] = ""
            
            elif scenario_type == 'source_valid_target_na':
                target_record['price'] = "NA"
            
            elif scenario_type == 'source_missing_target_na':
                target_record['price'] = "NA"
            
            elif scenario_type == 'source_missing_target_missing':
                target_record['price'] = ""
            
            elif scenario_type == 'negative_price':
                # Make the target price negative of source price
                # Source price should be valid and positive, target should be the negative value
                if source_record['price'] and source_record['price'] != "" and source_record['price'] != "NA":
                    try:
                        source_price_val = float(source_record['price'])
                        # Target price is the negative of source price
                        target_record['price'] = str(-abs(source_price_val))
                    except (ValueError, TypeError):
                        target_record['price'] = ""
                else:
                    target_record['price'] = ""
            
            elif scenario_type == 'no_issue':
                # Keep the price as computed from the rule (should match source)
                # Force it to exactly match the source price
                target_record['price'] = source_record['price']
            
            # Apply random inconsistency for scenarios 1-5 (not scenario 6 'no_target' or scenario 7 'no_issue')
            if inconsistent_field_list and scenario_type not in ['no_target', 'no_issue']:
                # Randomly choose one field from the inconsistent fields list
                field_to_make_inconsistent = random.choice(inconsistent_field_list)
                
                # If the field exists in the target record, prefix its value with 'INCONSISTENT_'
                if field_to_make_inconsistent in target_record:
                    original_value = target_record[field_to_make_inconsistent]
                    if original_value:  # Only modify if there's a value
                        target_record[field_to_make_inconsistent] = f'INCONSISTENT_{original_value}'
                    self.logger.debug(f"Record {record_id}: Made field '{field_to_make_inconsistent}' inconsistent")
            
            target_data.append(target_record)
        
        self.logger.info(f"Generated {len(target_data)} synthetic target records")
        return target_data

    def apply_rules_and_generate_keys(self, data: List[Dict[str, Any]], is_source: bool = True) -> List[Dict[str, Any]]:
        """Apply transformation rules and generate composite keys for matching."""
        processed_data = []
        
        for record in data:
            processed_record = record.copy()
            
            if is_source:
                transformed_values = []
                for col in self.id_columns:
                    if col != self.timestamp_config['source_col'] and col in self.transformation_rules:
                        try:
                            transformed_val = self.transformation_rules[col](record)
                            transformed_values.append(str(transformed_val))
                        except Exception as e:
                            self.logger.debug(f"Error applying rule for {col}: {e}")
                            transformed_values.append("")
                    elif col == self.timestamp_config['source_col']:
                        continue
                    else:
                        transformed_values.append(str(record.get(col, "")))
                
                processed_record['id_key'] = '--'.join(transformed_values)
            else:
                key_values = []
                for col in self.id_columns:
                    if col != self.timestamp_config['target_col']:
                        key_values.append(str(record.get(col, "")))
                processed_record['id_key'] = '--'.join(key_values)
            
            processed_data.append(processed_record)
        
        return processed_data

    def perform_matching(self, source_data: List[Dict[str, Any]], target_data: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """Perform matching between source and target data."""
        matched_records = []
        unmatched_records = []
        
        target_lookup = {}
        for target_record in target_data:
            key = target_record['id_key']
            if key not in target_lookup:
                target_lookup[key] = []
            target_lookup[key].append(target_record)
        
        for source_record in source_data:
            source_key = source_record['id_key']
            source_timestamp = int(float(source_record[self.timestamp_config['source_col']]))
            
            matches_for_this_source = []
            
            if source_key in target_lookup:
                for target_record in target_lookup[source_key]:
                    target_timestamp = int(float(target_record[self.timestamp_config['target_col']]))
                    
                    if abs(source_timestamp - target_timestamp) <= int(self.timestamp_config['delta']):
                        combined_record = {}
                        
                        for k, v in source_record.items():
                            combined_record[f'source_{k}'] = v
                        
                        for k, v in target_record.items():
                            combined_record[f'target_{k}'] = v
                        
                        matches_for_this_source.append(combined_record)
            
            if len(matches_for_this_source) == 0:
                unmatched_record = {}
                for k, v in source_record.items():
                    unmatched_record[f'source_{k}'] = v
                unmatched_records.append(unmatched_record)
            else:
                # Since we generate synthetic data with unique keys, we should only have one match
                matched_records.extend(matches_for_this_source)
        
        self.logger.info(f"Matching results: {len(matched_records)} matched, {len(unmatched_records)} unmatched")
        
        return {
            'unique': matched_records,
            'unmatched': unmatched_records
        }

    def perform_consistency_check(self, matched_records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Perform consistency check on matched records."""
        augmented_records = []
        
        for record in matched_records:
            augmented_record = record.copy()
            
            clean_row = {}
            for k, v in record.items():
                if k.startswith('source_'):
                    clean_row[k.replace('source_', '')] = v if v is not None else ""
            
            for col in self.consistency_check_columns:
                if col in self.consistency_rules:
                    try:
                        computed_value = self.consistency_rules[col](clean_row)
                        target_col_key = f'target_{col}'
                        
                        if (target_col_key not in record or 
                            not bool(re.fullmatch(str(computed_value), str(record.get(target_col_key, ""))))):
                            
                            # Special handling for price field: always empty in augmented_target
                            if col == 'price':
                                augmented_record[f'augmented_target_{col}'] = ""
                            else:
                                augmented_record[f'augmented_target_{col}'] = computed_value
                            self.logger.debug(f"Inconsistency found in {col}")
                    
                    except Exception as e:
                        self.logger.error(f"Error applying consistency rule for {col}: {e}")
            
            augmented_records.append(augmented_record)
        
        return augmented_records

    def generate_augmented_data_for_unmatched(self, unmatched_records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Generate complete augmented target data for unmatched records."""
        augmented_records = []
        columns_to_fill = self.id_columns + self.extra_columns_to_fill
        
        for record in unmatched_records:
            augmented_record = record.copy()
            
            clean_row = {}
            for k, v in record.items():
                if k.startswith('source_'):
                    clean_row[k.replace('source_', '')] = v if v is not None else ""
            
            for col in columns_to_fill:
                if col in self.transformation_rules:
                    try:
                        computed_value = self.transformation_rules[col](clean_row)
                        
                        # Special handling for price field: always empty in augmented_target
                        if col == 'price':
                            augmented_record[f'augmented_target_{col}'] = ""
                        else:
                            augmented_record[f'augmented_target_{col}'] = computed_value
                    except Exception as e:
                        self.logger.error(f"Error applying rule for {col}: {e}")
                        if col == 'price':
                            augmented_record[f'augmented_target_{col}'] = ""
                        else:
                            augmented_record[f'augmented_target_{col}'] = ""
            
            augmented_records.append(augmented_record)
        
        return augmented_records

    def write_simulation_output(self, results: Dict[str, List[Dict[str, Any]]]):
        """Write simulation results to output files and/or send to InsightFinder."""
        
        def convert_records_to_json(records):
            """Convert internal record format to JSON log format."""
            json_records = []
            
            for record in records:
                try:
                    timestamp_col = f"source_{self.timestamp_config['source_col']}"
                    timestamp = int(float(record.get(timestamp_col, 0)) * 1000)
                    
                    json_record = {"timestamp": timestamp}
                    
                    source_cols = [k.replace('source_', '') for k in record.keys() if k.startswith('source_') and k != 'source_id_key']
                    
                    if 'source' not in json_record:
                        json_record['source'] = {}
                    for col in source_cols:
                        source_key = f'source_{col}'
                        if source_key in record:
                            json_record['source'][col] = record[source_key] if record[source_key] is not None else ""
                    json_record['source']['env'] = self.source.lower()
                    
                    has_target_data = any(k.startswith('target_') for k in record.keys())
                    if has_target_data:
                        target_cols = [k.replace('target_', '') for k in record.keys() if k.startswith('target_') and k != 'target_id_key']
                        if 'target' not in json_record:
                            json_record['target'] = {}
                        for col in target_cols:
                            target_key = f'target_{col}'
                            if target_key in record:
                                json_record['target'][col] = record[target_key] if record[target_key] is not None else ""
                        json_record['target']['env'] = self.target.lower()
                    
                    has_augmented_data = any(k.startswith('augmented_target_') for k in record.keys())
                    if has_augmented_data:
                        augmented_cols = [k.replace('augmented_target_', '') for k in record.keys() if k.startswith('augmented_target_')]
                        if 'augmented_target' not in json_record:
                            json_record['augmented_target'] = {}
                        for col in augmented_cols:
                            augmented_key = f'augmented_target_{col}'
                            if augmented_key in record:
                                json_record['augmented_target'][col] = record[augmented_key] if record[augmented_key] is not None else ""
                        json_record['augmented_target']['env'] = self.target.lower()
                    
                    json_records.append(json_record)
                    
                except Exception as e:
                    self.logger.error(f"Error converting record: {e}")
            
            return json_records
        
        def write_records_to_files(json_records, log_path, record_type):
            """Write JSON records to file."""
            if not json_records:
                self.logger.info(f"No {record_type} records to write")
                return
            
            with open(log_path, 'w') as log_file:
                for json_record in json_records:
                    log_file.write(json.dumps(json_record) + '\n')
                
                self.logger.info(f"Finished writing {record_type} records to {log_path}")
                self.logger.info(f"Number of {record_type} records written: {len(json_records)}")
        
        def prepare_if_log_data(json_records, record_type):
            """Prepare log data in InsightFinder format."""
            if_log_data = []
            
            for json_record in json_records:
                try:
                    # InsightFinder log format
                    # 'tag' is the instance name in log format
                    if_entry = {
                        'eventId': str(json_record['timestamp']),
                        'tag': HOSTNAME,  # Instance name
                        'data': json.dumps(json_record)  # Store entire record as data
                    }
                    if_log_data.append(if_entry)
                except Exception as e:
                    self.logger.error(f"Error preparing IF log data: {e}")
            
            return if_log_data
        
        # Process each result type
        for result_type, records in [
            ('unique', results['unique']),
            ('unmatched', results['unmatched'])
        ]:
            if not records:
                self.logger.info(f"No {result_type} records to process")
                continue
            
            # Convert to JSON format
            json_records = convert_records_to_json(records)
            
            # Write to files if enabled
            if WRITE_TO_FILES:
                file_map = {
                    'unique': 'generated_unique.log',
                    'unmatched': 'generated_unmatched.log'
                }
                write_records_to_files(json_records, file_map[result_type], result_type)
            
            # Send to InsightFinder if enabled
            if SEND_TO_INSIGHTFINDER:
                if_log_data = prepare_if_log_data(json_records, result_type)
                send_data_to_insightfinder(self.logger, if_log_data, result_type)

    def run_simulation(self):
        """Run the complete simulation process."""
        self.logger.info("Starting price scenario simulation...")
        
        self.logger.info("Generating synthetic source data...")
        source_data = self.generate_synthetic_source_data()
        
        self.logger.info("Generating synthetic target data...")
        target_data = self.generate_synthetic_target_data(source_data)
        
        self.logger.info("Applying transformation rules and generating matching keys...")
        processed_source = self.apply_rules_and_generate_keys(source_data, is_source=True)
        processed_target = self.apply_rules_and_generate_keys(target_data, is_source=False)
        
        self.logger.info("Performing source-target matching...")
        matching_results = self.perform_matching(processed_source, processed_target)
        
        self.logger.info("Performing consistency checks on matched records...")
        matching_results['unique'] = self.perform_consistency_check(matching_results['unique'])
        
        self.logger.info("Generating augmented data for unmatched records...")
        matching_results['unmatched'] = self.generate_augmented_data_for_unmatched(matching_results['unmatched'])
        
        self.logger.info("Writing simulation output files...")
        self.write_simulation_output(matching_results)
        
        self.print_simulation_summary(matching_results)
        
        self.logger.info("Simulation completed successfully!")
        
        return matching_results

    def print_simulation_summary(self, results: Dict[str, List[Dict[str, Any]]]):
        """Print a summary of the simulation results."""
        print("\n" + "="*70)
        print("PRICE SCENARIO SIMULATION SUMMARY")
        print("="*70)
        
        print("\nScenario Configuration:")
        print(f"1. Source valid, target missing: {NUM_SOURCE_VALID_TARGET_MISSING}")
        print(f"2. Source valid, target NA: {NUM_SOURCE_VALID_TARGET_NA}")
        print(f"3. Source missing, target NA:")
        print(f"   - price1 & price2 both have data: {NUM_SOURCE_MISSING_TARGET_NA_P1_P2_BOTH}")
        print(f"   - price1 empty, price2 has data: {NUM_SOURCE_MISSING_TARGET_NA_P1_EMPTY_P2_DATA}")
        print(f"   - both price1 & price2 empty: {NUM_SOURCE_MISSING_TARGET_NA_BOTH_EMPTY}")
        print(f"4. Source missing, target missing:")
        print(f"   - price1 & price2 both have data: {NUM_SOURCE_MISSING_TARGET_MISSING_P1_P2_BOTH}")
        print(f"   - price1 empty, price2 has data: {NUM_SOURCE_MISSING_TARGET_MISSING_P1_EMPTY_P2_DATA}")
        print(f"   - both price1 & price2 empty: {NUM_SOURCE_MISSING_TARGET_MISSING_BOTH_EMPTY}")
        print(f"5. Negative price in target:")
        print(f"   - price1 & price2 both have data: {NUM_NEGATIVE_PRICE_P1_P2_BOTH}")
        print(f"   - price1 empty, price2 has data: {NUM_NEGATIVE_PRICE_P1_EMPTY_P2_DATA}")
        print(f"   - both price1 & price2 empty: {NUM_NEGATIVE_PRICE_BOTH_EMPTY}")
        print(f"6. No target: {NUM_NO_TARGET}")
        print(f"7. No issue (perfect match): {NUM_NO_ISSUE}")
        
        print(f"\nInconsistent fields configuration: {INCONSISTENT_FIELDS if INCONSISTENT_FIELDS else 'None'}")
        print(f"(One random field from this list will be prefixed with 'INCONSISTENT_' for scenarios 1-5)")
        
        print(f"\nTotal records: {self.total_records}")
        print(f"Unique matches: {len(results['unique'])}")
        print(f"Unmatched records: {len(results['unmatched'])}")
        
        if WRITE_TO_FILES:
            print("\nOutput files generated:")
            print("- generated_unique.log")
            print("- generated_unmatched.log")
        
        if SEND_TO_INSIGHTFINDER:
            print(f"\nData sent to InsightFinder:")
            print(f"- Project: {IF_PROJECT_NAME}")
            print(f"- URL: {IF_URL}")
        
        print("="*70)


def main():
    """Main function to run the simulation."""
    try:
        # Set up logging
        setup_logging(LOG_LEVEL.upper())
        logger = get_logger(__name__)
        
        logger.info("Starting Price Scenario Simulation")
        logger.info(f"Configuration loaded from: {CONFIG_PATH}")
        
        # Log scenario configuration
        logger.info("=" * 70)
        logger.info("SCENARIO CONFIGURATION")
        logger.info("=" * 70)
        logger.info(f"Scenario 1 (source valid, target missing): {NUM_SOURCE_VALID_TARGET_MISSING}")
        logger.info(f"Scenario 2 (source valid, target NA): {NUM_SOURCE_VALID_TARGET_NA}")
        logger.info(f"Scenario 3a (source missing, target NA, p1&p2 both): {NUM_SOURCE_MISSING_TARGET_NA_P1_P2_BOTH}")
        logger.info(f"Scenario 3b (source missing, target NA, p1 empty p2 data): {NUM_SOURCE_MISSING_TARGET_NA_P1_EMPTY_P2_DATA}")
        logger.info(f"Scenario 3c (source missing, target NA, both empty): {NUM_SOURCE_MISSING_TARGET_NA_BOTH_EMPTY}")
        logger.info(f"Scenario 4a (source missing, target missing, p1&p2 both): {NUM_SOURCE_MISSING_TARGET_MISSING_P1_P2_BOTH}")
        logger.info(f"Scenario 4b (source missing, target missing, p1 empty p2 data): {NUM_SOURCE_MISSING_TARGET_MISSING_P1_EMPTY_P2_DATA}")
        logger.info(f"Scenario 4c (source missing, target missing, both empty): {NUM_SOURCE_MISSING_TARGET_MISSING_BOTH_EMPTY}")
        logger.info(f"Scenario 5a (negative price, p1&p2 both): {NUM_NEGATIVE_PRICE_P1_P2_BOTH}")
        logger.info(f"Scenario 5b (negative price, p1 empty p2 data): {NUM_NEGATIVE_PRICE_P1_EMPTY_P2_DATA}")
        logger.info(f"Scenario 5c (negative price, both empty): {NUM_NEGATIVE_PRICE_BOTH_EMPTY}")
        logger.info(f"Scenario 6 (no target): {NUM_NO_TARGET}")
        logger.info(f"Scenario 7 (no issue - perfect match): {NUM_NO_ISSUE}")
        logger.info(f"Inconsistent fields: {INCONSISTENT_FIELDS if INCONSISTENT_FIELDS else 'None'}")
        logger.info("=" * 70)
        
        # Check and create InsightFinder project if enabled
        if SEND_TO_INSIGHTFINDER:
            logger.info("Checking InsightFinder project...")
            if not check_and_create_project(logger):
                logger.warning("Failed to verify InsightFinder project. Data may not be sent successfully.")
        
        # Initialize simulator
        simulator = PriceScenarioSimulator(CONFIG_PATH)
        
        # Run simulation
        results = simulator.run_simulation()
        
        logger.info("Price scenario simulation completed successfully!")
    
    except ValueError as e:
        # Handle validation errors without stack trace
        logger = get_logger(__name__)
        print(f"\n{str(e)}")
        return
        
    except Exception as e:
        logger = get_logger(__name__)
        logger.error(f"Simulation failed: {e}")
        raise


if __name__ == "__main__":
    main()
