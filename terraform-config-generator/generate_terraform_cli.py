#!/usr/bin/env python3
"""
Terraform Configuration Generator for InsightFinder Projects (CLI Version)
Generates Terraform configuration from InsightFinder API raw data.

Usage:
    python generate_terraform_cli.py --settings settings.json --keywords keywords.json --output output.tf
    python generate_terraform_cli.py --settings settings.json --keywords keywords.json --project-name "My Project" --system-name "My System"
"""

import json
import sys
import argparse
from pathlib import Path


def parse_project_settings(settings_json_str):
    """Parse the nested JSON string from settingList."""
    settings = json.loads(settings_json_str)
    return settings.get('DATA', {})


def format_terraform_value(value):
    """Format a Python value for Terraform syntax."""
    if isinstance(value, bool):
        return 'true' if value else 'false'
    elif isinstance(value, str):
        # Escape special characters
        escaped = value.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
        return f'"{escaped}"'
    elif isinstance(value, (int, float)):
        return str(value)
    elif isinstance(value, dict):
        return f'jsonencode({json.dumps(value)})'
    elif isinstance(value, list):
        return f'jsonencode({json.dumps(value)})'
    elif value is None:
        return '""'
    else:
        return str(value)


def convert_keywords_to_log_labels(keywords_data):
    """Convert keywords JSON to log_label_settings format."""
    log_labels = []
    
    # Map keyword types to label types
    keyword_type_mapping = {
        'whitelist': 'whitelist',
        'trainingWhitelist': 'trainingWhitelist',
        'trainingBlacklistLabels': 'trainingBlacklist',
        'extractionBlacklist': 'extractionBlacklist',
        'featurelist': 'featurelist',
        'incidentlist': 'incidentlist',
        'triagelist': 'triagelist',
        'anomalyFeatureLabels': 'anomalyFeatureLabel',
        'dataFilterLabels': 'dataFilterLabel',
        'patternNameLabels': 'patternName',
        'instanceNameLabels': 'instanceName',
        'dataQualityCheckLabels': 'dataQualityCheck'
    }
    
    for keyword_type, label_type in keyword_type_mapping.items():
        if keyword_type in keywords_data and keywords_data[keyword_type]:
            log_labels.append({
                'label_type': label_type,
                'log_label_string': keywords_data[keyword_type]
            })
    
    return log_labels


def generate_terraform_config(project_name, settings_data, keywords_data, servicenow_data=None,
                              system_name="Default System", 
                              base_url="https://stg.insightfinder.com", include_provider=True):
    """Generate Terraform configuration from project settings and keywords."""
    
    # Detect if this is a ServiceNow project
    is_servicenow = servicenow_data is not None
    
    # Extract project creation config
    if is_servicenow:
        project_creation_config = {
            'data_type': 'Log',
            'instance_type': 'ServiceNow',
            'project_cloud_type': 'ServiceNow',
            'insight_agent_type': 'Custom',
            'servicenow_table': '-=-=-=-=-= edit this field -=-=-=-=-= incident or problem'
        }
    else:
        project_creation_config = {
            'data_type': 'Log',
            'instance_type': 'OnPremise',
            'project_cloud_type': 'OnPremise',
            'insight_agent_type': 'Historical'
        }
    
    # Generate log_label_settings
    log_labels = convert_keywords_to_log_labels(keywords_data)
    
    # Start building the Terraform configuration
    config = []
    
    if include_provider:
        config.append('terraform {')
        config.append('  required_providers {')
        config.append('    insightfinder = {')
        config.append('      source = "insightfinder/insightfinder"')
        config.append('      version = ">= 1.0.0"')
        config.append('    }')
        config.append('  }')
        config.append('}')
        config.append('')
        config.append('provider "insightfinder" {')
        config.append(f'  base_url = "{base_url}"')
        config.append('}')
        config.append('')
    
    # Sanitize project name for resource name
    resource_name = project_name.lower().replace('-', '_').replace(' ', '_')
    
    config.append(f'resource "insightfinder_project" "{resource_name}" {{')
    config.append(f'  project_name = "{project_name}"')
    config.append(f'  system_name  = "{system_name}"')
    config.append('')
    
    # Project creation config
    config.append('  project_creation_config = {')
    config.append(f'    data_type          = "{project_creation_config["data_type"]}"')
    config.append(f'    instance_type      = "{project_creation_config["instance_type"]}"')
    config.append(f'    project_cloud_type = "{project_creation_config["project_cloud_type"]}"')
    config.append(f'    insight_agent_type = "{project_creation_config["insight_agent_type"]}"')
    if is_servicenow:
        config.append(f'    servicenow_table   = "{project_creation_config["servicenow_table"]}"')
    config.append('  }')
    config.append('')
    
    # Map settings to Terraform attributes
    attribute_mapping = {
        'projectDisplayName': 'project_display_name',
        'projectTimeZone': 'project_time_zone',
        'retentionTime': 'retention_time',
        'UBLRetentionTime': 'ubl_retention_time',
        'alertAverageTime': 'alert_average_time',
        'alertHourlyCost': 'alert_hourly_cost',
        'anomalyDetectionMode': 'anomaly_detection_mode',
        'anomalySamplingInterval': 'anomaly_sampling_interval',
        'avgPerIncidentDowntimeCost': 'avg_per_incident_downtime_cost',
        'baseValueSetting': 'base_value_setting',
        'cValue': 'c_value',
        'causalMinDelay': 'causal_min_delay',
        'causalPredictionSetting': 'causal_prediction_setting',
        'cdfSetting': 'cdf_setting',
        'coldEventThreshold': 'cold_event_threshold',
        'coldNumberLimit': 'cold_number_limit',
        'collectAllRareEventsFlag': 'collect_all_rare_events_flag',
        'dailyModelSpan': 'daily_model_span',
        'disableLogCompressEvent': 'disable_log_compress_event',
        'disableModelKeywordStatsCollection': 'disable_model_keyword_stats_collection',
        'emailSetting': 'email_setting',
        'enableAnomalyScoreEscalation': 'enable_anomaly_score_escalation',
        'enableHotEvent': 'enable_hot_event',
        'enableNewAlertEmail': 'enable_new_alert_email',
        'enableStreamDetection': 'enable_stream_detection',
        'escalationAnomalyScoreThreshold': 'escalation_anomaly_score_threshold',
        'featureOutlierSensitivity': 'feature_outlier_sensitivity',
        'featureOutlierThreshold': 'feature_outlier_threshold',
        'hotEventCalmDownPeriod': 'hot_event_calm_down_period',
        'hotEventDetectionMode': 'hot_event_detection_mode',
        'hotEventThreshold': 'hot_event_threshold',
        'hotNumberLimit': 'hot_number_limit',
        'ignoreAnomalyScoreThreshold': 'ignore_anomaly_score_threshold',
        'ignoreInstanceForKB': 'ignore_instance_for_kb',
        'incidentPredictionEventLimit': 'incident_prediction_event_limit',
        'incidentPredictionWindow': 'incident_prediction_window',
        'incidentRelationSearchWindow': 'incident_relation_search_window',
        'instanceConvertFlag': 'instance_convert_flag',
        'instanceDownEnable': 'instance_down_enable',
        'instanceGroupingUpdate': 'instance_grouping_update',
        'isEdgeBrain': 'is_edge_brain',
        'isGroupingByInstance': 'is_grouping_by_instance',
        'isTracePrompt': 'is_trace_prompt',
        'keywordFeatureNumber': 'keyword_feature_number',
        'keywordSetting': 'keyword_setting',
        'largeProject': 'large_project',
        'llmEvaluationSetting': 'llm_evaluation_setting',
        'logAnomalyEventBaseScore': 'log_anomaly_event_base_score',
        'logDetectionMinCount': 'log_detection_min_count',
        'logDetectionSize': 'log_detection_size',
        'logPatternLimitLevel': 'log_pattern_limit_level',
        'logToLogSettingList': 'log_to_log_setting_list',
        'maxLogModelSize': 'max_log_model_size',
        'maxWebHookRequestSize': 'max_web_hook_request_size',
        'maximumDetectionWaitTime': 'maximum_detection_wait_time',
        'maximumRootCauseResultSize': 'maximum_root_cause_result_size',
        'maximumThreads': 'maximum_threads',
        'minIncidentPredictionWindow': 'min_incident_prediction_window',
        'minValidModelSpan': 'min_valid_model_span',
        'modelKeywordSetting': 'model_keyword_setting',
        'multiHopSearchLevel': 'multi_hop_search_level',
        'multiHopSearchLimit': 'multi_hop_search_limit',
        'multiLineFlag': 'multi_line_flag',
        'newAlertFlag': 'new_alert_flag',
        'newPatternNumberLimit': 'new_pattern_number_limit',
        'newPatternRange': 'new_pattern_range',
        'nlpFlag': 'nlp_flag',
        'normalEventCausalFlag': 'normal_event_causal_flag',
        'pValue': 'p_value',
        'predictionCountThreshold': 'prediction_count_threshold',
        'predictionProbabilityThreshold': 'prediction_probability_threshold',
        'predictionRuleActiveCondition': 'prediction_rule_active_condition',
        'predictionRuleActiveThreshold': 'prediction_rule_active_threshold',
        'predictionRuleFalsePositiveThreshold': 'prediction_rule_false_positive_threshold',
        'predictionRuleInactiveThreshold': 'prediction_rule_inactive_threshold',
        'prettyJsonConvertorFlag': 'pretty_json_convertor_flag',
        'projectModelFlag': 'project_model_flag',
        'proxy': 'proxy',
        'rareAnomalyType': 'rare_anomaly_type',
        'rareEventAlertThresholds': 'rare_event_alert_thresholds',
        'rareNumberLimit': 'rare_number_limit',
        'rootCauseCountThreshold': 'root_cause_count_threshold',
        'rootCauseLogMessageSearchRange': 'root_cause_log_message_search_range',
        'rootCauseProbabilityThreshold': 'root_cause_probability_threshold',
        'rootCauseRankSetting': 'root_cause_rank_setting',
        'samplingInterval': 'sampling_interval',
        'sharedUsernames': 'shared_usernames',
        'showInstanceDown': 'show_instance_down',
        'similaritySensitivity': 'similarity_sensitivity',
        'trainingFilter': 'training_filter',
        'webhookAlertDampening': 'webhook_alert_dampening',
        'webhookBlackListSetStr': 'webhook_black_list_set_str',
        'webhookCriticalKeywordSetStr': 'webhook_critical_keyword_set_str',
        'webhookHeaderList': 'webhook_header_list',
        'webhookTypeSetStr': 'webhook_type_set_str',
        'webhookUrl': 'webhook_url',
        'whitelistNumberLimit': 'whitelist_number_limit',
        'zoneNameKey': 'zone_name_key',
    }
    
    # Add all mapped attributes
    for api_key, tf_key in attribute_mapping.items():
        if api_key in settings_data:
            value = settings_data[api_key]
            formatted_value = format_terraform_value(value)
            config.append(f'  {tf_key} = {formatted_value}')
    
    # Add ServiceNow settings if present
    if servicenow_data:
        config.append('')
        config.append('  # ServiceNow third-party settings')
        config.append('  project_servicenow_settings = {')
        
        # Host (required)
        config.append(f'    host                 = "{servicenow_data.get("host", "")}"')

        # Authentication
        config.append(f'    servicenow_user      = "{servicenow_data.get("serviceNowUser", "")}"')
        config.append(f'    servicenow_password  = "{servicenow_data.get("serviceNowPassword", "")}"')
        config.append(f'    client_id            = "{servicenow_data.get("clientId", "")}"')
        config.append(f'    client_secret        = "{servicenow_data.get("clientSecret", "")}"')
        
        # Configuration fields
        config.append(f'    instance_field       = "{servicenow_data.get("instanceField", "")}"')
        config.append(f'    instance_field_regex = "{servicenow_data.get("instanceFieldRegex", "")}"')
        config.append(f'    timestamp_format     = "{servicenow_data.get("timestampFormat", "")}"')
        config.append(f'    sysparm_query        = "{servicenow_data.get("sysparmQuery", "")}"')
        config.append(f'    proxy                = "{servicenow_data.get("proxy", "")}"')
        
        # Additional fields
        fields_json = json.dumps(servicenow_data.get('additionalFields', {}))
        config.append(f'    additional_fields    = {fields_json}')
        
        config.append('  }')
    
    # Add log_label_settings if present
    if log_labels:
        config.append('')
        config.append('  log_label_settings = [')
        for i, label in enumerate(log_labels):
            config.append('      {')
            config.append(f'        label_type       = "{label["label_type"]}",')
            config.append(f'        log_label_string = jsonencode({json.dumps(label["log_label_string"])})')
            if i < len(log_labels) - 1:
                config.append('      },')
            else:
                config.append('      }')
        config.append('    ]')
    
    config.append('}')
    
    return '\n'.join(config)


def main():
    """Main function to generate Terraform configuration from CLI arguments."""
    parser = argparse.ArgumentParser(
        description='Generate Terraform configuration from InsightFinder API raw data',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Using JSON files
  python generate_terraform_cli.py --settings settings.json --keywords keywords.json
  
  # Specify output file
  python generate_terraform_cli.py --settings settings.json --keywords keywords.json --output myproject.tf
  
  # With ServiceNow settings
  python generate_terraform_cli.py --settings settings.json --keywords keywords.json \\
      --servicenow servicenow.json --output servicenow_project.tf
  
  # Override project and system names
  python generate_terraform_cli.py --settings settings.json --keywords keywords.json \\
      --project-name "My Project" --system-name "My System"
  
  # Append to existing Terraform file (no provider block)
  python generate_terraform_cli.py --settings settings.json --keywords keywords.json \\
      --output existing.tf --no-provider
        """
    )
    
    parser.add_argument('--settings', required=True, help='Path to settings JSON file')
    parser.add_argument('--keywords', required=True, help='Path to keywords JSON file')
    parser.add_argument('--servicenow', help='Path to ServiceNow settings JSON file (optional)')
    parser.add_argument('--output', '-o', help='Output Terraform file (default: <project_name>.tf)')
    parser.add_argument('--project-name', help='Override project name from settings')
    parser.add_argument('--system-name', default='Default System', help='System name (default: Default System)')
    parser.add_argument('--base-url', default='https://stg.insightfinder.com', 
                       help='InsightFinder base URL (default: https://stg.insightfinder.com)')
    parser.add_argument('--no-provider', action='store_true', 
                       help='Skip provider block (for appending to existing config)')
    
    args = parser.parse_args()
    
    # Load settings
    try:
        with open(args.settings, 'r') as f:
            settings_raw = json.load(f)
    except FileNotFoundError:
        print(f"Error: Settings file not found: {args.settings}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in settings file: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Load keywords
    try:
        with open(args.keywords, 'r') as f:
            keywords_raw = json.load(f)
    except FileNotFoundError:
        print(f"Error: Keywords file not found: {args.keywords}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in keywords file: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Parse project name and settings from settings file
    project_name = args.project_name
    settings_data = None
    
    if "settingList" in settings_raw:
        for proj_name, settings_str in settings_raw["settingList"].items():
            if not project_name:
                project_name = proj_name
            settings_data = parse_project_settings(settings_str)
            break
    else:
        print("Error: No 'settingList' found in settings data", file=sys.stderr)
        sys.exit(1)
    
    if not project_name:
        print("Error: No project found in settings data", file=sys.stderr)
        sys.exit(1)
    
    keywords_data = keywords_raw.get("keywords", {})
    
    # Load ServiceNow settings if provided
    servicenow_data = None
    if args.servicenow:
        try:
            with open(args.servicenow, 'r') as f:
                servicenow_data = json.load(f)
            print(f"📄 ServiceNow settings loaded from: {args.servicenow}")
        except FileNotFoundError:
            print(f"Warning: ServiceNow file not found: {args.servicenow}", file=sys.stderr)
        except json.JSONDecodeError as e:
            print(f"Warning: Invalid JSON in ServiceNow file: {e}", file=sys.stderr)
    
    # Generate Terraform configuration
    terraform_config = generate_terraform_config(
        project_name=project_name,
        settings_data=settings_data,
        keywords_data=keywords_data,
        servicenow_data=servicenow_data,
        system_name=args.system_name,
        base_url=args.base_url,
        include_provider=not args.no_provider
    )
    
    # Determine output file
    if args.output:
        output_file = args.output
    else:
        output_file = f"{project_name.lower().replace('-', '_')}.tf"
    
    # Write to file
    with open(output_file, 'w') as f:
        f.write(terraform_config)
    
    print(f"✅ Terraform configuration generated: {output_file}")
    print(f"   Project: {project_name}")
    print(f"   System: {args.system_name}")
    print("\nNext steps:")
    print("1. Review the generated file")
    print("2. Run: terraform init")
    print("3. Run: terraform plan")
    print("4. Run: terraform apply")


if __name__ == "__main__":
    main()
