#!/usr/bin/env python3
"""
Terraform Configuration Generator for InsightFinder Projects (CLI Version)
Generates Terraform configuration from InsightFinder API raw data.

Usage:
    # Project only
    python generate_terraform_cli.py --settings settings.json --keywords keywords.json --output output.tf

    # Project + system-level settings
    python3 generate_terraform_cli.py --settings sample_settings.json --keywords sample_keywords.json \
        --system-name "Citizen Cane Demo System (STG)" \
        --kb-global sample_kb_global.json \
        --kb-incident-prediction sample_kb_incident_prediction.json \
        --notifications sample_notifications.json \
        --output output.tf
"""

import json
import re
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
            "whitelist":                       "whitelist",
			"trainingWhitelist":               "trainingWhitelist",
			"trainingBlacklistLabels":         "blacklist",
			"featurelist":                     "featurelist",
			"incidentlist":                    "incidentlist",
			"triagelist":                      "triagelist",
			"patternNameLabels":               "patternName",
			"patternSignatureLabels":          "patternSignature",
			"patternMatchRegexLabels":         "patternMatchRegex",
			"patternIgnoreRegexLabels":        "patternIgnoreRegex",
			"customActionLabels":              "customAction",
			"logEventIDLabels":                "logEventID",
			"logSeverityLabels":               "logSeverity",
			"logStatusCodeLabels":             "logStatusCode",
			"alertEventTypeLabels":            "alertEventType",
			"anomalyFeatureLabels":            "anomalyFeature",
			"dataFilterLabels":                "dataFilter",
			"instanceNameLabels":              "instanceName",
			"dataQualityCheckLabels":          "dataQualityCheck",
			"incidentFieldVerificationLabels": "incidentFieldVerification",
			"incidentPriorityLabels":          "incidentPriority",
			"extractionBlacklist":             "extractionBlacklist",
    }
    
    for keyword_type, label_type in keyword_type_mapping.items():
        if keyword_type in keywords_data and keywords_data[keyword_type]:
            log_labels.append({
                'label_type': label_type,
                'log_label_string': keywords_data[keyword_type]
            })
    
    return log_labels


def convert_json_keys_to_terraform(json_keys_data, summary_settings=None, metafield_settings=None, dampening_field_settings=None):
    """Convert JSON keys data to json_key_settings format for Terraform.
    
    Args:
        json_keys_data: List of dicts with jsonKey and type
        summary_settings: List of field names to mark as summary
        metafield_settings: List of field names to mark as metafield
        dampening_field_settings: List of field names to mark as dampening field
    
    Returns:
        List of formatted terraform json_key_settings
    """
    json_key_settings = []
    summary_set = set(summary_settings) if summary_settings else set()
    metafield_set = set(metafield_settings) if metafield_settings else set()
    dampening_field_set = set(dampening_field_settings) if dampening_field_settings else set()
    
    if not isinstance(json_keys_data, list):
        return json_key_settings
    
    for key_item in json_keys_data:
        json_key = key_item.get('jsonKey') or key_item.get('json_key')
        key_type = key_item.get('type', 'string')
        
        if json_key:
            setting = {
                'json_key': json_key,
                'type': key_type,
                'summary_setting': json_key in summary_set,
                'metafield_setting': json_key in metafield_set,
                'dampening_field_setting': json_key in dampening_field_set
            }
            json_key_settings.append(setting)
    
    return json_key_settings


def _sn_safe_name(account, service_host):
    """Generate a safe Terraform resource/variable name suffix from account and service host."""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(service_host)
        host_part = parsed.netloc or parsed.path
    except Exception:
        host_part = service_host
    combined = f"{account}_{host_part}"
    return re.sub(r'[^a-z0-9_]', '_', combined.lower())


def _parse_servicenow_entry(entry):
    """Parse a single ServiceNow entry from extServiceAllInfo API response.

    Returns a dict with normalized fields, or None if the entry is invalid.
    """
    account = entry.get("account", "")
    service_host = entry.get("service_host", "")
    if not account or not service_host:
        return None

    config = {
        "account": account,
        "service_host": service_host,
        "password": entry.get("password", ""),
        "proxy": entry.get("proxy", ""),
        "dampening_period": int(entry.get("dampeningPeriod", 0)),
        "app_id": entry.get("appId", ""),
        "app_key": entry.get("appKey", ""),
        "system_ids": [],
        "system_names": [],
        "options": [],
        "content_option": [],
        "service_now_field": entry.get("serviceNowField", ""),
        "content_source": entry.get("contentSource", ""),
        "trigger_window_in_mills": 0,
        "table_mapping": {},
    }

    # Parse options JSON array string
    options_str = entry.get("options", "")
    if options_str:
        try:
            config["options"] = json.loads(options_str)
        except (json.JSONDecodeError, TypeError):
            pass

    # Parse configs JSON string for systemIds, contentOption, triggerWindowInMills
    configs_str = entry.get("configs", "")
    if configs_str:
        try:
            configs = json.loads(configs_str)
            config["system_ids"] = [str(sid) for sid in configs.get("systemIds", [])]
            config["content_option"] = [str(co) for co in configs.get("contentOption", [])]
            if not config["service_now_field"]:
                config["service_now_field"] = configs.get("serviceNowField", "")
            if not config["content_source"]:
                config["content_source"] = configs.get("contentSource", "")
            trigger = configs.get("triggerWindowInMills", 0)
            if trigger:
                config["trigger_window_in_mills"] = int(float(trigger))
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

    # Parse tableMapping array of [projectName, tableName] pairs
    table_mapping_raw = entry.get("tableMapping", [])
    if isinstance(table_mapping_raw, list):
        for row in table_mapping_raw:
            if isinstance(row, list) and len(row) == 2:
                config["table_mapping"][str(row[0])] = str(row[1])

    # Determine auth type from appId/appKey presence
    config["auth_type"] = "oauth" if (config["app_id"] and config["app_key"]) else "basic"

    return config


def generate_servicenow_env_config(sn_entries, include_provider=True, base_url="",
                                   use_vars=False, system_id_to_name=None):
    """Generate Terraform configuration for insightfinder_servicenow resources.

    One resource block is generated per entry. This is an environment-level resource,
    not tied to any specific system.

    Args:
        sn_entries: List of parsed ServiceNow config dicts (from _parse_servicenow_entry).
        include_provider: Whether to include terraform/provider blocks.
        base_url: InsightFinder base URL (used in provider block when include_provider=True).
        use_vars: If True, sensitive fields (password, app_key) reference Terraform variables
                  named var.sn_<safe_name>_password / var.sn_<safe_name>_app_key.
                  If False, outputs empty strings with TODO comments.
        system_id_to_name: Optional dict mapping system IDs to display names. When provided,
                           system_ids are resolved to names for the system_names attribute.

    Returns:
        HCL string for all insightfinder_servicenow resources.
    """
    if not sn_entries:
        return ""

    if system_id_to_name is None:
        system_id_to_name = {}

    lines = []

    if include_provider:
        lines += [
            'terraform {',
            '  required_providers {',
            '    insightfinder = {',
            '      source  = "insightfinder/insightfinder"',
            '      version = ">= 1.6.1"',
            '    }',
            '  }',
            '}',
            '',
            'provider "insightfinder" {',
            f'  base_url = "{base_url}"',
            '}',
            '',
        ]

    for config in sn_entries:
        account = config["account"]
        service_host = config["service_host"]
        safe_name = _sn_safe_name(account, service_host)
        var_prefix = f"sn_{safe_name}"

        # Resolve system names: prefer pre-resolved names, then look up by ID, then fall back to ID
        system_names = list(config.get("system_names", []))
        if not system_names:
            system_names = [system_id_to_name.get(sid, sid) for sid in config.get("system_ids", [])]

        lines.append(f'resource "insightfinder_servicenow" "{safe_name}" {{')
        lines.append(f'  account      = "{account}"')
        lines.append(f'  service_host = "{service_host}"')

        if use_vars:
            lines.append(f'  password     = var.{var_prefix}_password')
        else:
            lines.append(f'  password     = ""  # TODO: set password for {account} @ {service_host}')

        lines.append(f'  auth_type    = "{config["auth_type"]}"')

        if config.get("app_id"):
            lines.append(f'  app_id       = "{config["app_id"]}"')
        if config.get("app_key"):
            if use_vars:
                lines.append(f'  app_key      = var.{var_prefix}_app_key')
            else:
                lines.append(f'  app_key      = ""  # TODO: set app_key for {account} @ {service_host}')

        proxy = config.get("proxy", "")
        escaped_proxy = proxy.replace('"', '\\"')
        lines.append(f'  proxy        = "{escaped_proxy}"')

        lines.append(f'  dampening_period = {config["dampening_period"]}')
        lines.append('')

        if system_names:
            names_json = json.dumps(system_names)
            lines.append(f'  system_names = {names_json}')
        elif config.get("system_ids"):
            ids_comment = ", ".join(f'"{sid}"' for sid in config["system_ids"])
            lines.append(f'  # TODO: replace system IDs with display names: {ids_comment}')
            lines.append(f'  system_names = []')

        if config.get("options"):
            lines.append(f'  options        = {json.dumps(config["options"])}')

        if config.get("content_option"):
            lines.append(f'  content_option = {json.dumps(config["content_option"])}')

        if config.get("service_now_field"):
            escaped = config["service_now_field"].replace('"', '\\"')
            lines.append(f'  service_now_field = "{escaped}"')

        if config.get("content_source"):
            escaped = config["content_source"].replace('"', '\\"')
            lines.append(f'  content_source = "{escaped}"')

        if config.get("trigger_window_in_mills"):
            lines.append(f'  trigger_window_in_mills = {config["trigger_window_in_mills"]}')

        if config.get("table_mapping"):
            lines.append('  table_mapping = {')
            for project, table in config["table_mapping"].items():
                proj_e = project.replace('"', '\\"')
                table_e = table.replace('"', '\\"')
                lines.append(f'    "{proj_e}" = "{table_e}"')
            lines.append('  }')

        lines.append('}')
        lines.append('')

    return '\n'.join(lines)


def generate_terraform_config(project_name, settings_data, keywords_data, servicenow_data=None,
                              json_keys_data=None, summary_settings=None, metafield_settings=None,
                              dampening_field_settings=None,
                              system_name="NBC Stage", 
                              base_url="https://nbc.insightfinder.com", include_provider=True):
    """Generate Terraform configuration from project settings and keywords.
    
    Args:
        project_name: Name of the project
        settings_data: Project settings dictionary
        keywords_data: Keywords configuration
        servicenow_data: ServiceNow settings (optional)
        json_keys_data: JSON key definitions (optional)
        summary_settings: List of fields to include in summary (optional)
        metafield_settings: List of fields to include in metafield (optional)
        dampening_field_settings: List of fields to include in dampening field (optional)
        system_name: System name
        base_url: InsightFinder base URL
        include_provider: Whether to include provider block
    """
    
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
    
    # Generate json_key_settings
    json_key_settings = convert_json_keys_to_terraform(
        json_keys_data or [],
        summary_settings=summary_settings,
        metafield_settings=metafield_settings,
        dampening_field_settings=dampening_field_settings
    )
    
    # Start building the Terraform configuration
    config = []
    
    if include_provider:
        config.append('terraform {')
        config.append('  required_providers {')
        config.append('    insightfinder = {')
        config.append('      source = "insightfinder/insightfinder"')
        config.append('      version = ">= 1.6.1"')
        config.append('    }')
        config.append('  }')
        config.append('}')
        config.append('')
        config.append('provider "insightfinder" {')
        config.append(f'  base_url = "{base_url}"')
        config.append('}')
        config.append('')
    
    # Sanitize project name for resource name
    resource_name = re.sub(r'[^a-z0-9_]', '_', project_name.lower())
    
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
            # For emailSetting: ensure awSeverityLevel is always present, defaulting to "Major"
            if api_key == 'emailSetting' and isinstance(value, dict):
                if 'awSeverityLevel' not in value:
                    value = dict(value)  # shallow copy to avoid mutating original
                    value['awSeverityLevel'] = 'Major'
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
    
    # Add json_key_settings if present
    if json_key_settings:
        config.append('')
        config.append('  json_key_settings = [')
        for i, key_setting in enumerate(json_key_settings):
            config.append('    {')
            config.append(f'      json_key               = "{key_setting["json_key"]}"')
            config.append(f'      type                   = "{key_setting["type"]}"')
            config.append(f'      summary_setting        = {format_terraform_value(key_setting["summary_setting"])}')
            config.append(f'      metafield_setting      = {format_terraform_value(key_setting["metafield_setting"])}')
            config.append(f'      dampening_field_setting = {format_terraform_value(key_setting["dampening_field_setting"])}')
            if i < len(json_key_settings) - 1:
                config.append('    },')
            else:
                config.append('    }')
        config.append('  ]')
    
    config.append('}')
    
    return '\n'.join(config)


def generate_system_settings_config(system_name: str, kb_global_data: dict | None,
                                    kb_incident_data: dict | None,
                                    notifications_data: dict | None,
                                    system_name_expr: str | None = None) -> str:
    """Generate an insightfinder_system_settings Terraform resource block.

    Args:
        system_name: Human-readable system name (used as the resource identifier).
        kb_global_data: Dict from sample_kb_global.json (globalknowledgebasesetting API response).
        kb_incident_data: Dict from sample_kb_incident_prediction.json (IncidentPredictionSetting API response).
        notifications_data: Dict from sample_notifications.json (healthviewsetting API response, single system).
        system_name_expr: HCL expression for system_name attribute. Defaults to a quoted literal.

    Returns:
        Terraform HCL string for the resource block.
    """
    resource_name = re.sub(r'[^a-z0-9_]', '_', system_name.lower())
    sn_value = system_name_expr if system_name_expr is not None else f'"{system_name}"'
    lines = []
    lines.append(f'resource "insightfinder_system_settings" "{resource_name}" {{')
    lines.append(f'  system_name = {sn_value}')

    # --- knowledgebase_settings block ---
    has_kb = kb_global_data or kb_incident_data
    if has_kb:
        lines.append('')
        lines.append('  knowledgebase_settings = {')

        if kb_global_data:
            # Scalar global KB fields
            kb_field_map = [
                ('enableGlobalKnowledgeBase',      'enable_global_knowledge_base'),
                ('compositeValidThreshold',        'composite_valid_threshold'),
                ('timelineTopK',                   'timeline_top_k'),
                ('enableIgnoreInstancePrediction', 'enable_ignore_instance_prediction'),
                ('predictionSource',               'prediction_source'),
                ('shareSystemType',                'share_system_type'),
                ('actionExecutionTime',            'action_execution_time'),
                ('autoFixValidationWindow',        'auto_fix_validation_window'),
                ('filterSelfToSelf',               'filter_self_to_self'),
                ('ruleSourceType',                 'rule_source_type'),
            ]
            for api_key, tf_key in kb_field_map:
                if api_key in kb_global_data:
                    lines.append(f'    {tf_key} = {format_terraform_value(kb_global_data[api_key])}')

            # Complex array field: satelliteSystemSet stored as JSON string
            sat = kb_global_data.get('satelliteSystemSet')
            if sat is not None:
                lines.append(f'    satellite_system_set = {format_terraform_value(sat)}')

        if kb_incident_data:
            ip_field_map = [
                ('ruleActiveThreshold',           'rule_active_threshold'),
                ('ruleInactiveThreshold',         'rule_inactive_threshold'),
                ('ruleActiveCondition',           'rule_active_condition'),
                ('falsePositiveTolerance',        'false_positive_tolerance'),
                ('kbTrainingLength',              'kb_training_length'),
                ('tolerance',                     'tolerance'),
                ('enableInsensitiveRuleMatching', 'enable_insensitive_rule_matching'),
            ]
            for api_key, tf_key in ip_field_map:
                if api_key in kb_incident_data:
                    lines.append(f'    {tf_key} = {format_terraform_value(kb_incident_data[api_key])}')

        lines.append('  }')

    # --- notifications_settings block ---
    if notifications_data:
        lines.append('')
        lines.append('  notifications_settings = {')

        # Scalar notification fields
        notif_field_map = [
            ('order',                              'order'),
            ('hideFlag',                           'hide_flag'),
            ('aggregationInterval',               'aggregation_interval'),
            ('enableSplunkExport',                 'enable_splunk_export'),
            ('predictionEmail',                    'prediction_email'),
            ('alertHealthScore',                   'alert_health_score'),
            ('alertFrequency',                     'alert_frequency'),
            ('emailDampeningPeriod',               'email_dampening_period'),
            ('alertsEmailDampeningPeriod',         'alerts_email_dampening_period'),
            ('predictionEmailDampeningPeriod',     'prediction_email_dampening_period'),
            ('enableSystemDownEmailAlert',         'enable_system_down_email_alert'),
            ('onlySendWithRCA',                    'only_send_with_rca'),
            ('enableIncidentPredictionEmailAlert', 'enable_incident_prediction_email_alert'),
            ('enableIncidentDetectionEmailAlert',  'enable_incident_detection_email_alert'),
            ('enableAlertsEmail',                  'enable_alerts_email'),
            ('enableHealthEmailAlert',             'enable_health_email_alert'),
            ('alertEmail',                         'alert_email'),
            ('healthAlertEmail',                   'health_alert_email'),
            ('incidentDetectionEmail',             'incident_detection_email'),
            ('enableRootCauseEmailAlert',          'enable_root_cause_email_alert'),
            ('rootCauseEmail',                     'root_cause_email'),
            ('incidentDampeningWindow',            'incident_dampening_window'),
        ]
        for api_key, tf_key in notif_field_map:
            if api_key in notifications_data:
                lines.append(f'    {tf_key} = {format_terraform_value(notifications_data[api_key])}')

        # Complex map fields serialized as JSON strings
        for api_key, tf_key in [('incidentCountThreshold', 'incident_count_threshold'),
                                  ('assignmentMap', 'assignment_map')]:
            val = notifications_data.get(api_key)
            if val is not None:
                lines.append(f'    {tf_key} = {format_terraform_value(val)}')

        lines.append('  }')

    lines.append('}')
    return '\n'.join(lines)


def main():
    """Main function to generate Terraform configuration from CLI arguments."""
    parser = argparse.ArgumentParser(
        description='Generate Terraform configuration from InsightFinder API raw data',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Project-level only
  python generate_terraform_cli.py --settings sample_settings.json --keywords sample_keywords.json

  # Specify output file
  python generate_terraform_cli.py --settings sample_settings.json --keywords sample_keywords.json \\
      --output myproject.tf

  # With JSON key settings
  python generate_terraform_cli.py --settings sample_settings.json --keywords sample_keywords.json \\
      --json-keys sample_jsonkey.json --summary-metafield sample_summary_and_metafields.json

  # With system-level settings (fetched via fetch_insightfinder_data.py --system-name ...)
  python generate_terraform_cli.py --settings sample_settings.json --keywords sample_keywords.json \\
      --system-name "My System" \\
      --kb-global sample_kb_global.json \\
      --kb-incident-prediction sample_kb_incident_prediction.json \\
      --notifications sample_notifications.json

  # Full example: project + system settings + ServiceNow
  python generate_terraform_cli.py --settings sample_settings.json --keywords sample_keywords.json \\
      --servicenow servicenow.json \\
      --system-name "My System" \\
      --kb-global sample_kb_global.json \\
      --notifications sample_notifications.json \\
      --output full_config.tf

  # Append to existing Terraform file (no provider block)
  python generate_terraform_cli.py --settings sample_settings.json --keywords sample_keywords.json \\
      --output existing.tf --no-provider
        """
    )
    
    parser.add_argument('--settings', help='Path to settings JSON file (sample_settings.json)')
    parser.add_argument('--keywords', help='Path to keywords JSON file (sample_keywords.json)')
    parser.add_argument('--servicenow-external-settings', dest='servicenow_external_settings',
                        help='Path to external ServiceNow settings JSON '
                             '(extServiceAllInfo API response). Generates insightfinder_servicenow '
                             'resources at environment level (not tied to any system).')
    parser.add_argument('--servicenow', help='Path to ServiceNow settings JSON file (optional)')
    parser.add_argument('--json-keys', help='Path to JSON keys definition file (optional, sample_jsonkey.json)')
    parser.add_argument('--summary-metafield',
                        help='Path to summary and metafield settings JSON file (optional, sample_summary_and_metafields.json)')
    parser.add_argument('--output', '-o', help='Output Terraform file (default: <project_name>.tf)')
    parser.add_argument('--project-name', help='Override project name from settings')
    parser.add_argument('--system-name', default='NBC Stage',
                        help='System display name used in insightfinder_system_settings resource (default: NBC Stage)')
    parser.add_argument('--base-url', default='https://nbc.insightfinder.com',
                        help='InsightFinder base URL (default: https://nbc.insightfinder.com)')
    parser.add_argument('--no-provider', action='store_true',
                        help='Skip provider block (for appending to existing config)')
    # System-level settings files (produced by fetch_insightfinder_data.py --system-name ...)
    parser.add_argument('--kb-global', dest='kb_global',
                        help='Path to global knowledge base settings JSON (sample_kb_global.json)')
    parser.add_argument('--kb-incident-prediction', dest='kb_incident_prediction',
                        help='Path to incident prediction settings JSON (sample_kb_incident_prediction.json)')
    parser.add_argument('--notifications', dest='notifications',
                        help='Path to notifications/health-view settings JSON (sample_notifications.json)')
    
    args = parser.parse_args()

    # Validate argument combinations
    if not args.settings and not args.servicenow_external_settings:
        parser.error("at least one of --settings or --servicenow-external-settings is required")
    if args.settings and not args.keywords:
        parser.error("--keywords is required when --settings is provided")

    # -----------------------------------------------------------------------
    # ServiceNow-only mode: generate insightfinder_servicenow resources from
    # the external settings API response (environment-level, no system/project).
    # -----------------------------------------------------------------------
    if args.servicenow_external_settings and not args.settings:
        try:
            with open(args.servicenow_external_settings, 'r') as f:
                ext_raw = json.load(f)
        except FileNotFoundError:
            print(f"Error: File not found: {args.servicenow_external_settings}", file=sys.stderr)
            sys.exit(1)
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON in external settings file: {e}", file=sys.stderr)
            sys.exit(1)

        entries_raw = ext_raw.get("extServiceAllInfo", [])
        sn_entries = [_parse_servicenow_entry(e) for e in entries_raw]
        sn_entries = [e for e in sn_entries if e is not None]

        if not sn_entries:
            print("Warning: No valid ServiceNow configurations found in the input file.", file=sys.stderr)
            sys.exit(0)

        output_file = args.output or "servicenow.tf"
        sn_hcl = generate_servicenow_env_config(
            sn_entries=sn_entries,
            include_provider=not args.no_provider,
            base_url=args.base_url,
            use_vars=False,  # CLI mode: output placeholders, not var refs
        )

        with open(output_file, 'w') as f:
            f.write(sn_hcl)

        print(f"\nServiceNow Terraform configuration generated: {output_file}")
        print(f"   Configurations: {len(sn_entries)}")
        for e in sn_entries:
            print(f"   - {e['account']} @ {e['service_host']}")
        print("\nNote: Replace TODO placeholders (password, app_key, system_names) before applying.")
        print("Next steps:")
        print("1. Review and update placeholder values in the generated file")
        print("2. Run: terraform init")
        print("3. Run: terraform plan")
        print("4. Run: terraform apply")
        return

    # -----------------------------------------------------------------------
    # Project mode (existing behaviour): load settings and generate project TF
    # -----------------------------------------------------------------------

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
    
    # Load JSON keys if provided
    json_keys_data = None
    if args.json_keys:
        try:
            with open(args.json_keys, 'r') as f:
                json_keys_data = json.load(f)
            print(f"📄 JSON keys loaded from: {args.json_keys}")
        except FileNotFoundError:
            print(f"Warning: JSON keys file not found: {args.json_keys}", file=sys.stderr)
        except json.JSONDecodeError as e:
            print(f"Warning: Invalid JSON in JSON keys file: {e}", file=sys.stderr)
    
    # Load summary and metafield settings if provided, otherwise default to empty lists
    summary_settings = []
    metafield_settings = []
    dampening_field_settings = []
    if args.summary_metafield:
        try:
            with open(args.summary_metafield, 'r') as f:
                summary_meta_data = json.load(f)
                summary_settings = summary_meta_data.get('summarySetting', [])
                metafield_settings = summary_meta_data.get('metaFieldSetting', [])
                dampening_field_settings = summary_meta_data.get('dampeningFieldSetting', [])
            print(f"📄 Summary and metafield settings loaded from: {args.summary_metafield}")
        except FileNotFoundError:
            print(f"Warning: Summary/metafield file not found: {args.summary_metafield}", file=sys.stderr)
        except json.JSONDecodeError as e:
            print(f"Warning: Invalid JSON in summary/metafield file: {e}", file=sys.stderr)
    else:
        print(":information_source:  No summary/metafield file provided - all settings default to false")
    
    # Load system-level settings files (optional)
    kb_global_data = None
    if args.kb_global:
        try:
            with open(args.kb_global, 'r') as f:
                kb_global_data = json.load(f)
            print(f"Loaded global KB settings from: {args.kb_global}")
        except FileNotFoundError:
            print(f"Warning: KB global file not found: {args.kb_global}", file=sys.stderr)
        except json.JSONDecodeError as e:
            print(f"Warning: Invalid JSON in KB global file: {e}", file=sys.stderr)

    kb_incident_data = None
    if args.kb_incident_prediction:
        try:
            with open(args.kb_incident_prediction, 'r') as f:
                kb_incident_data = json.load(f)
            print(f"Loaded incident prediction settings from: {args.kb_incident_prediction}")
        except FileNotFoundError:
            print(f"Warning: KB incident prediction file not found: {args.kb_incident_prediction}", file=sys.stderr)
        except json.JSONDecodeError as e:
            print(f"Warning: Invalid JSON in KB incident prediction file: {e}", file=sys.stderr)

    notifications_data = None
    if args.notifications:
        try:
            with open(args.notifications, 'r') as f:
                notifications_data = json.load(f)
            print(f"Loaded notifications settings from: {args.notifications}")
        except FileNotFoundError:
            print(f"Warning: Notifications file not found: {args.notifications}", file=sys.stderr)
        except json.JSONDecodeError as e:
            print(f"Warning: Invalid JSON in notifications file: {e}", file=sys.stderr)

    # Generate Terraform configuration
    terraform_config = generate_terraform_config(
        project_name=project_name,
        settings_data=settings_data,
        keywords_data=keywords_data,
        servicenow_data=servicenow_data,
        json_keys_data=json_keys_data,
        summary_settings=summary_settings,
        metafield_settings=metafield_settings,
        dampening_field_settings=dampening_field_settings,
        system_name=args.system_name,
        base_url=args.base_url,
        include_provider=not args.no_provider
    )

    # Append system-level settings block if any system data was provided
    has_system_settings = kb_global_data or kb_incident_data or notifications_data
    system_settings_config = ""
    if has_system_settings:
        system_settings_config = "\n\n" + generate_system_settings_config(
            system_name=args.system_name,
            kb_global_data=kb_global_data,
            kb_incident_data=kb_incident_data,
            notifications_data=notifications_data,
        )

    # Determine output file
    if args.output:
        output_file = args.output
    else:
        output_file = f"{project_name.lower().replace('-', '_')}.tf"

    # Write to file
    with open(output_file, 'w') as f:
        f.write(terraform_config)
        if system_settings_config:
            f.write(system_settings_config)

    print(f"\nTerraform configuration generated: {output_file}")
    print(f"   Project: {project_name}")
    print(f"   System:  {args.system_name}")
    if has_system_settings:
        blocks = []
        if kb_global_data or kb_incident_data:
            blocks.append("knowledgebase_settings")
        if notifications_data:
            blocks.append("notifications_settings")
        print(f"   System settings blocks: {', '.join(blocks)}")

    # Also generate environment-level ServiceNow config if provided alongside project
    if args.servicenow_external_settings:
        try:
            with open(args.servicenow_external_settings, 'r') as f:
                ext_raw = json.load(f)
            entries_raw = ext_raw.get("extServiceAllInfo", [])
            sn_entries = [_parse_servicenow_entry(e) for e in entries_raw]
            sn_entries = [e for e in sn_entries if e is not None]
            if sn_entries:
                sn_output = "servicenow.tf"
                sn_hcl = generate_servicenow_env_config(
                    sn_entries=sn_entries,
                    include_provider=False,  # already emitted by the project file
                    base_url=args.base_url,
                    use_vars=False,
                )
                with open(sn_output, 'w') as f:
                    f.write(sn_hcl)
                print(f"   ServiceNow env config: {sn_output} ({len(sn_entries)} resource(s))")
        except (FileNotFoundError, json.JSONDecodeError, Exception) as e:
            print(f"Warning: Could not generate ServiceNow env config: {e}", file=sys.stderr)

    print("\nNext steps:")
    print("1. Review the generated file")
    print("2. Run: terraform init")
    print("3. Run: terraform plan")
    print("4. Run: terraform apply")


if __name__ == "__main__":
    main()
