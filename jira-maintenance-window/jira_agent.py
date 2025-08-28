#!/usr/bin/env python3
"""
Jira Maintenance Window Agent

This script connects to a Jira instance using API credentials, applies configurable
filters, and extracts ticket metadata based on status criteria.

Author: AI Assistant
Date: August 27, 2025
"""

import configparser
import json
import csv
import logging
import sys
import os
from typing import List, Dict, Any, Optional
import argparse
from datetime import datetime

try:
    import requests
    from requests.auth import HTTPBasicAuth
except ImportError:
    print("Error: requests library not found. Install it with: pip install requests")
    sys.exit(1)


class JiraAgent:
    """Main class for interacting with Jira API and filtering tickets."""
    
    def __init__(self, config_file: str = "conf.d/config.ini"):
        """Initialize the Jira agent with configuration."""
        self.config = configparser.ConfigParser()
        self.config.read(config_file)
        
        # Setup logging
        self._setup_logging()
        
        # Jira connection details
        self.jira_url = self.config.get('jira', 'url').rstrip('/')
        self.api_token = self.config.get('jira', 'api_token')
        self.username = self.config.get('jira', 'username')
        
        # Session for API calls
        self.session = requests.Session()
        self.session.auth = HTTPBasicAuth(self.username, self.api_token)
        self.session.headers.update({
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        })
        
        self.logger.info("Jira Agent initialized")
    
    def _setup_logging(self):
        """Setup logging based on configuration."""
        log_level = getattr(logging, self.config.get('logging', 'level', fallback='INFO'))
        
        # Configure logging
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        self.logger = logging.getLogger('JiraAgent')
        
        # Add file handler if specified
        log_file = self.config.get('logging', 'log_file', fallback=None)
        if log_file:
            file_handler = logging.FileHandler(log_file)
            file_handler.setLevel(log_level)
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)
    
    def test_connection(self) -> bool:
        """Test connection to Jira instance."""
        try:
            url = f"{self.jira_url}/rest/api/2/myself"
            response = self.session.get(url)
            response.raise_for_status()
            
            user_info = response.json()
            self.logger.info(f"Successfully connected to Jira as: {user_info.get('displayName', 'Unknown')}")
            return True
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Failed to connect to Jira: {e}")
            return False
    
    def get_actual_status_names(self, config_statuses: List[str]) -> List[str]:
        """Get actual status names from Jira that match the configured statuses (case insensitive)."""
        try:
            # Get available statuses from Jira
            url = f"{self.jira_url}/rest/api/2/status"
            response = self.session.get(url)
            response.raise_for_status()
            
            jira_statuses = response.json()
            jira_status_names = [status.get('name', '') for status in jira_statuses]
            
            # Match configured statuses with actual Jira statuses (case insensitive)
            matched_statuses = []
            config_statuses_lower = [status.strip().lower() for status in config_statuses]
            
            for jira_status in jira_status_names:
                if jira_status.lower() in config_statuses_lower:
                    matched_statuses.append(jira_status)
                    self.logger.info(f"Matched status: '{jira_status}' (from config)")
            
            # Log any unmatched statuses
            for config_status in config_statuses:
                config_lower = config_status.strip().lower()
                if not any(matched.lower() == config_lower for matched in matched_statuses):
                    self.logger.warning(f"Status '{config_status.strip()}' not found in Jira")
            
            return matched_statuses
            
        except requests.exceptions.RequestException as e:
            self.logger.warning(f"Failed to get Jira statuses: {e}")
            return []
    
    def get_actual_issue_types(self, config_types: List[str]) -> List[str]:
        """Get actual issue type names from Jira that match the configured types (case insensitive)."""
        try:
            # Get available issue types from Jira
            url = f"{self.jira_url}/rest/api/2/issuetype"
            response = self.session.get(url)
            response.raise_for_status()
            
            jira_types = response.json()
            jira_type_names = [issue_type.get('name', '') for issue_type in jira_types]
            
            # Match configured types with actual Jira types (case insensitive)
            matched_types = []
            config_types_lower = [issue_type.strip().lower() for issue_type in config_types]
            
            for jira_type in jira_type_names:
                if jira_type.lower() in config_types_lower:
                    matched_types.append(jira_type)
                    self.logger.info(f"Matched issue type: '{jira_type}' (from config)")
            
            # Log any unmatched types
            for config_type in config_types:
                config_lower = config_type.strip().lower()
                if not any(matched.lower() == config_lower for matched in matched_types):
                    self.logger.warning(f"Issue type '{config_type.strip()}' not found in Jira")
            
            return matched_types
            
        except requests.exceptions.RequestException as e:
            self.logger.warning(f"Failed to get Jira issue types: {e}")
            return []
    
    def build_type_filter_jql(self, base_jql: str, types: List[str], mode: str) -> str:
        """Build JQL with issue type filtering (case insensitive)."""
        # Get actual type names from Jira to match case-insensitively
        actual_types = self.get_actual_issue_types(types)
        
        if not actual_types:
            self.logger.warning("No matching issue types found, using original names")
            actual_types = [issue_type.strip() for issue_type in types]
        
        type_list = [f'"{issue_type}"' for issue_type in actual_types]
        type_jql = f"issuetype {'NOT IN' if mode == 'exclude' else 'IN'} ({', '.join(type_list)})"
        
        if base_jql.strip():
            combined_jql = f"({base_jql}) AND {type_jql}"
        else:
            combined_jql = type_jql
        
        self.logger.info(f"JQL with type filter: {combined_jql}")
        return combined_jql
    
    def build_status_filter_jql(self, base_jql: str, statuses: List[str], mode: str) -> str:
        """Build JQL with status filtering (case insensitive)."""
        # Get actual status names from Jira to match case-insensitively
        actual_statuses = self.get_actual_status_names(statuses)
        
        if not actual_statuses:
            self.logger.warning("No matching statuses found, using original names")
            actual_statuses = [status.strip() for status in statuses]
        
        status_list = [f'"{status}"' for status in actual_statuses]
        status_jql = f"status {'NOT IN' if mode == 'exclude' else 'IN'} ({', '.join(status_list)})"
        
        if base_jql.strip():
            combined_jql = f"({base_jql}) AND {status_jql}"
        else:
            combined_jql = status_jql
        
        self.logger.info(f"Final JQL: {combined_jql}")
        return combined_jql
    
    def search_issues(self, jql: str, fields: List[str]) -> List[Dict[str, Any]]:
        """Search for issues using JQL."""
        all_issues = []
        start_at = 0
        max_results = 50  # Jira's default limit
        
        try:
            while True:
                url = f"{self.jira_url}/rest/api/2/search"
                params = {
                    'jql': jql,
                    'startAt': start_at,
                    'maxResults': max_results,
                    'fields': ','.join(fields)
                }
                
                response = self.session.get(url, params=params)
                response.raise_for_status()
                
                data = response.json()
                issues = data.get('issues', [])
                all_issues.extend(issues)
                
                self.logger.info(f"Retrieved {len(issues)} issues (total so far: {len(all_issues)})")
                
                # Check if we've got all issues
                if len(issues) < max_results or start_at + len(issues) >= data.get('total', 0):
                    break
                
                start_at += max_results
            
            self.logger.info(f"Total issues retrieved: {len(all_issues)}")
            return all_issues
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Failed to search issues: {e}")
            return []
    
    def extract_issue_data(self, issues: List[Dict[str, Any]], requested_fields: List[str]) -> List[Dict[str, Any]]:
        """Extract and format issue data (case-insensitive for fields, types, and statuses), with support for YAML value mapping."""
        import yaml
        extracted_data = []
        # Map of field names to extraction logic (with safe None handling)
        field_extractors = {
            'summary': lambda f: f.get('summary', '') if f else '',
            'status': lambda f: f.get('status', {}).get('name', '') if f and f.get('status') else '',
            'assignee': lambda f: f.get('assignee', {}).get('displayName', '') if f and f.get('assignee') else 'Unassigned',
            'reporter': lambda f: f.get('reporter', {}).get('displayName', '') if f and f.get('reporter') else '',
            'created': lambda f: f.get('created', '') if f else '',
            'updated': lambda f: f.get('updated', '') if f else '',
            'priority': lambda f: f.get('priority', {}).get('name', '') if f and f.get('priority') else '',
            'description': lambda f: f.get('description', '') if f else '',
            'components': lambda f: [comp.get('name', '') for comp in f.get('components', [])] if f and f.get('components') else [],
            'labels': lambda f: f.get('labels', []) if f else [],
            'resolution': lambda f: f.get('resolution', {}).get('name', '') if f and f.get('resolution') else '',
            'issuetype': lambda f: f.get('issuetype', {}).get('name', '') if f and f.get('issuetype') else '',
            'project': lambda f: f.get('project', {}).get('key', '') if f and f.get('project') else '',
        }
        # Load custom field mapping from config (case-insensitive keys)
        custom_field_map = {k.lower(): v for k, v in self.config.items('custom_field_map')} if self.config.has_section('custom_field_map') else {}
        # Load custom field value mapping (YAML) from config [custom_field_mapping]
        custom_field_value_mapping = {}
        if self.config.has_section('custom_field_mapping'):
            for k, v in self.config.items('custom_field_mapping'):
                try:
                    with open(v, 'r') as f:
                        custom_field_value_mapping[k.lower()] = yaml.safe_load(f)
                except Exception as e:
                    self.logger.warning(f"Could not load mapping file {v} for field {k}: {e}")

        for issue in issues:
            issue_data = {
                'key': issue.get('key', ''),
                'id': issue.get('id', '')
            }
            fields = issue.get('fields', {})
            for field in requested_fields:
                try:
                    field_lower = field.strip().lower()
                    # Standard fields
                    if field_lower in field_extractors:
                        issue_data[field_lower] = field_extractors[field_lower](fields)
                    # Custom fields
                    elif field_lower in custom_field_map:
                        mapped_field = custom_field_map[field_lower]
                        value = fields.get(mapped_field, '')
                        # If a value mapping is defined for this field, use it
                        if field_lower in custom_field_value_mapping and value in custom_field_value_mapping[field_lower]:
                            mapped_value = custom_field_value_mapping[field_lower][value]
                            issue_data[field_lower] = mapped_value
                        else:
                            issue_data[field_lower] = value
                    # Fallback for any other field
                    elif field_lower not in ['key', 'id']:
                        value = fields.get(field, '') if fields else ''
                        if value == '' and fields:
                            for k, v in fields.items():
                                if k.lower() == field_lower:
                                    value = v
                                    break
                        issue_data[field_lower] = value
                except Exception as e:
                    self.logger.warning(f"Error extracting field '{field}' from issue {issue.get('key', 'unknown')}: {e}")
                    issue_data[field.strip().lower()] = ''
            extracted_data.append(issue_data)
        return extracted_data
    
    def save_output(self, data: List[Dict[str, Any]], output_format: str, output_file: Optional[str] = None):
        """Save or display the output data."""
        if output_format.lower() == 'json':
            json_data = json.dumps(data, indent=2, default=str)
            if output_file:
                with open(output_file, 'w') as f:
                    f.write(json_data)
                self.logger.info(f"Data saved to {output_file}")
            else:
                print(json_data)
        
        elif output_format.lower() == 'csv':
            if not data:
                self.logger.warning("No data to save")
                return
            
            fieldnames = data[0].keys()
            
            if output_file:
                with open(output_file, 'w', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    for row in data:
                        # Convert lists to strings for CSV
                        csv_row = {}
                        for k, v in row.items():
                            if isinstance(v, list):
                                csv_row[k] = ', '.join(str(item) for item in v)
                            else:
                                csv_row[k] = str(v)
                        writer.writerow(csv_row)
                self.logger.info(f"Data saved to {output_file}")
            else:
                writer = csv.DictWriter(sys.stdout, fieldnames=fieldnames)
                writer.writeheader()
                for row in data:
                    csv_row = {}
                    for k, v in row.items():
                        if isinstance(v, list):
                            csv_row[k] = ', '.join(str(item) for item in v)
                        else:
                            csv_row[k] = str(v)
                    writer.writerow(csv_row)
        
        elif output_format.lower() == 'console':
            print(f"\n{'='*80}")
            print(f"JIRA TICKETS SUMMARY - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"{'='*80}")
            print(f"Total tickets found: {len(data)}\n")
            
            for i, issue in enumerate(data, 1):
                print(f"{i}. {issue.get('key', 'N/A')} - {issue.get('summary', 'No summary')}")
                print(f"   Status: {issue.get('status', 'N/A')}")
                print(f"   Assignee: {issue.get('assignee', 'N/A')}")
                print(f"   Created: {issue.get('created', 'N/A')}")
                print("-" * 40)
    
    def run(self):
        """Main execution method."""
        self.logger.info("Starting Jira Agent execution")
        
        # Test connection
        if not self.test_connection():
            self.logger.error("Cannot connect to Jira. Please check your configuration.")
            return False
        
        # Get base JQL from config
        base_jql = self.config.get('filter', 'base_jql', fallback='')
        if base_jql and base_jql.strip():
            self.logger.info("Using base_jql from config as the base filter JQL")
        else:
            base_jql = ""
            self.logger.warning("No base_jql specified, using empty base JQL")
        
        # Get status filter configuration
        status_mode = self.config.get('status_filter', 'mode', fallback='exclude')
        status_list = [s.strip() for s in self.config.get('status_filter', 'statuses', fallback='').split(',') if s.strip()]
        
        # Apply status filter
        if status_list:
            jql = self.build_status_filter_jql(base_jql, status_list, status_mode)
        else:
            jql = base_jql
            self.logger.warning("No status filter specified")
        
        # Get type filter configuration
        type_mode = self.config.get('type_filter', 'mode', fallback='')
        type_list = [t.strip() for t in self.config.get('type_filter', 'types', fallback='').split(',') if t.strip()]
        
        # Apply type filter if configured
        if type_list and type_mode:
            jql = self.build_type_filter_jql(jql, type_list, type_mode)
            self.logger.info(f"Applied type filter: {type_mode} {type_list}")
        elif type_list and not type_mode:
            self.logger.warning("Type list specified but no mode set - skipping type filter")
        else:
            self.logger.info("No type filter specified")
        
        # Get output configuration
        output_fields = [f.strip() for f in self.config.get('output', 'fields', fallback='key,summary,status').split(',')]
        output_format = self.config.get('output', 'format', fallback='json')
        output_file = self.config.get('output', 'output_file', fallback=None)

        # Load custom field mapping from config (case-insensitive keys)
        custom_field_map = {k.lower(): v for k, v in self.config.items('custom_field_map')} if self.config.has_section('custom_field_map') else {}

        # Build the list of fields to request from Jira: all output fields, plus any mapped custom fields
        fields_to_request = set()
        for f in output_fields:
            fields_to_request.add(f)
            mapped = custom_field_map.get(f.strip().lower())
            if mapped:
                fields_to_request.add(mapped)
        fields_to_request = list(fields_to_request)

        # Search for issues
        self.logger.info("Searching for issues...")
        issues = self.search_issues(jql, fields_to_request)

        if not issues:
            self.logger.warning("No issues found matching the criteria")
            return True

        # Extract and format data (only output friendly names)
        extracted_data = self.extract_issue_data(issues, output_fields)

        # Convert any timestamp-like string to epoch millis in the output
        from datetime import datetime
        import re
        timestamp_regex = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}([+-]\d{4})$")
        def to_epoch_millis(val):
            try:
                # Try parsing with timezone offset
                dt = datetime.strptime(val, "%Y-%m-%dT%H:%M:%S.%f%z")
                return int(dt.timestamp() * 1000)
            except Exception:
                return val

        for item in extracted_data:
            for k, v in item.items():
                if isinstance(v, str) and timestamp_regex.match(v):
                    item[k] = to_epoch_millis(v)

        # Save output
        self.save_output(extracted_data, output_format, output_file)

        self.logger.info("Jira Agent execution completed successfully")
        return True


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Jira Maintenance Window Agent')
    parser.add_argument('--config', '-c', default='conf.d/config.ini',
                       help='Path to configuration file (default: conf.d/config.ini)')
    parser.add_argument('--test-connection', action='store_true',
                       help='Test connection to Jira and exit')
    
    args = parser.parse_args()
    
    if not os.path.exists(args.config):
        print(f"Error: Configuration file '{args.config}' not found.")
        print("Please copy conf.d/config.ini.template to conf.d/config.ini and update with your settings.")
        sys.exit(1)
    
    try:
        agent = JiraAgent(args.config)
        
        if args.test_connection:
            if agent.test_connection():
                print("✅ Connection to Jira successful!")
                sys.exit(0)
            else:
                print("❌ Connection to Jira failed!")
                sys.exit(1)
        
        # Run the main process
        success = agent.run()
        sys.exit(0 if success else 1)
        
    except KeyboardInterrupt:
        print("\n⏹️  Operation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
