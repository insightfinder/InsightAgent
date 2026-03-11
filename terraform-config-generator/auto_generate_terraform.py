#!/usr/bin/env python3
"""
Fully automated Terraform configuration generator for InsightFinder.

Reads config.yaml and auto-discovers all owned systems + projects via API,
then generates a complete TerraformFiles directory structure.

Usage:
    python auto_generate_terraform.py --config config.yaml
    python auto_generate_terraform.py --config config.yaml --env NBC
    python auto_generate_terraform.py --config config.yaml --output-dir TerraformFiles
    python auto_generate_terraform.py --config config.yaml --dry-run

config.yaml format:
    Delay: 2  # seconds between project API calls (0 = no delay)
    NBC:
      base_url: https://nbc.insightfinder.com/
      username: nbcAdmin
      licensekey: xyzzzz
      project_types: [metric, log]
      terraform_version: 1.7.0        # optional; defaults to ">= 1.6.1"
      only_process:                   # optional; omit to process everything
        systems: ["System A"]         # process all projects in these systems
        projects: ["Project X"]       # also process these projects (original system folder structure)
    PROD:
      base_url: https://app.insightfinder.com/
      username: mustafa
      licensekey: xyzzz
      project_types: [log]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import yaml
except ImportError:
    print("Missing dependency: pyyaml. Install with: pip install pyyaml", file=sys.stderr)
    raise

try:
    import requests
except ImportError:
    print("Missing dependency: requests. Install with: pip install requests", file=sys.stderr)
    raise

# Reuse field-generation helpers from existing script
from generate_terraform_cli import (
    format_terraform_value,
    convert_keywords_to_log_labels,
    convert_json_keys_to_terraform,
    generate_system_settings_config,
    parse_project_settings,
)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def tf_resource_name(name: str) -> str:
    """Convert any string to a valid Terraform resource identifier."""
    return re.sub(r'[^a-z0-9_]', '_', name.lower())


# Map config project_type strings to API dataType values (case-insensitive)
DATATYPE_MAP: Dict[str, List[str]] = {
    "log":        ["log"],
    "metric":     ["metric"],
    "alert":      ["log", "alert"],
    "trace":      ["trace"],
    "deployment": ["deployment"],
}


def load_config(config_path: str) -> Dict[str, Any]:
    with open(config_path) as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def make_session(no_ssl_verify: bool = False) -> requests.Session:
    s = requests.Session()
    s.verify = not no_ssl_verify
    return s


def _get(session: requests.Session, url: str, headers: Dict[str, str],
         params: Optional[Dict] = None, max_retries: int = 3) -> Optional[requests.Response]:
    for attempt in range(1, max_retries + 1):
        try:
            resp = session.get(url, headers=headers, params=params, timeout=30)
            return resp
        except requests.RequestException as e:
            if attempt < max_retries:
                time.sleep(attempt)
            else:
                print(f"  Request failed after {max_retries} attempts: {e}", file=sys.stderr)
                return None
    return None


def fetch_json(session: requests.Session, url: str, headers: Dict[str, str],
               params: Optional[Dict] = None) -> Optional[Any]:
    resp = _get(session, url, headers, params)
    if resp is None:
        return None
    if resp.status_code != 200:
        print(f"  Warning: HTTP {resp.status_code} for {url}", file=sys.stderr)
        return None
    try:
        return resp.json()
    except ValueError:
        return None


def api_headers(username: str, api_key: str, use_license: bool = False) -> Dict[str, str]:
    key_header = "X-License-Key" if use_license else "X-API-Key"
    return {
        "X-User-Name": username,
        key_header: api_key,
        "Content-Type": "application/json",
    }


# ---------------------------------------------------------------------------
# InsightFinder API calls
# ---------------------------------------------------------------------------

def get_own_systems(session: requests.Session, host: str,
                    username: str, api_key: str, customer_name: str) -> List[Dict]:
    """Return list of system dicts from ownSystemArr only."""
    url = f"{host.rstrip('/')}/api/external/v1/systemframework"
    headers = api_headers(username, api_key)
    params = {"customerName": customer_name, "needDetail": "true", "tzOffset": "0"}

    data = fetch_json(session, url, headers, params)
    if not data:
        print(f"  Could not fetch system framework for {customer_name}", file=sys.stderr)
        return []

    systems = []
    for s in data.get("ownSystemArr", []):
        try:
            system = json.loads(s) if isinstance(s, str) else s
            systems.append(system)
        except (json.JSONDecodeError, TypeError):
            continue
    return systems


def get_system_display_name(system: Dict) -> str:
    return (
        system.get("systemDisplayName")
        or (system.get("systemKey") or {}).get("systemName")
        or system.get("systemName")
        or "unknown"
    )


def get_system_id(system: Dict) -> str:
    return (
        (system.get("systemKey") or {}).get("systemName")
        or system.get("systemId")
        or system.get("systemName")
        or ""
    )


def filter_projects_by_type(project_list: List[Dict], project_types: List[str]) -> List[Dict]:
    if not project_types:
        return project_list
    allowed = set()
    for pt in project_types:
        allowed.update(DATATYPE_MAP.get(pt.lower(), [pt.lower()]))
    return [p for p in project_list if (p.get("dataType") or "").lower() in allowed]


def fetch_project_data(session: requests.Session, host: str, username: str,
                       api_key: str, customer_name: str, project_name: str) -> Dict:
    """Fetch all project-level API data. Returns a dict with all fetched data."""
    headers = api_headers(username, api_key)
    lic_headers = api_headers(username, api_key, use_license=True)
    base = host.rstrip('/')
    result: Dict[str, Any] = {}

    # 1. Keywords
    kw = fetch_json(session, f"{base}/api/external/v1/projectkeywords",
                    headers, {"projectName": project_name})
    result["keywords"] = (kw or {}).get("keywords", {})

    # 2. Project settings
    project_list_param = [{"projectName": project_name, "customerName": customer_name}]
    settings = fetch_json(session, f"{base}/api/external/v1/watch-tower-setting",
                          headers, {"projectList": json.dumps(project_list_param)})
    result["settings"] = settings

    # 3. Summary/metafield settings
    summary = fetch_json(session, f"{base}/api/external/v1/logsummarysettings",
                         headers, {"projectName": project_name})
    result["summary"] = summary

    # 4. JSON key settings
    jsonkeys = fetch_json(session, f"{base}/api/external/v1/logjsontype",
                          headers, {"projectName": project_name})
    result["jsonkeys"] = jsonkeys

    # 5. ServiceNow settings (gracefully skip non-SN projects)
    sn = fetch_json(session, f"{base}/api/external/v1/thirdpartysetting",
                    lic_headers,
                    {"projectName": project_name, "cloudType": "ServiceNow",
                     "tzOffset": "-18000000"})
    # Only keep if response looks like real SN data
    result["servicenow"] = sn if sn and isinstance(sn, dict) and sn.get("host") else None

    return result


def fetch_system_level_settings(session: requests.Session, host: str, username: str,
                                api_key: str, customer_name: str,
                                system_id: str) -> Tuple[Any, Any, Any]:
    """Return (kb_global, kb_incident, notifications) for the given system."""
    headers = api_headers(username, api_key)
    base = host.rstrip('/')
    sys_ids_json = json.dumps([system_id])

    kb_global = fetch_json(session, f"{base}/api/external/v1/globalknowledgebasesetting",
                           headers, {"customerName": customer_name, "systemIds": sys_ids_json})
    if isinstance(kb_global, list) and kb_global:
        kb_global = kb_global[0]

    kb_incident = fetch_json(session, f"{base}/api/external/v2/IncidentPredictionSetting",
                             headers, {"customerName": customer_name, "systemIds": sys_ids_json})
    if isinstance(kb_incident, list) and kb_incident:
        kb_incident = kb_incident[0]

    all_notif = fetch_json(session, f"{base}/api/external/v2/healthviewsetting",
                           headers, {"customerName": customer_name})
    notifications = None
    if isinstance(all_notif, dict) and system_id in all_notif:
        notifications = all_notif[system_id]

    return kb_global, kb_incident, notifications


# ---------------------------------------------------------------------------
# Terraform file generators
# ---------------------------------------------------------------------------

def _versions_tf(env_name: str, system_name: str, terraform_version: str = ">= 1.6.1") -> str:
    key = f"{env_name}/{system_name}/terraform.tfstate"
    return f'''\
terraform {{
  required_providers {{
    insightfinder = {{
      source  = "insightfinder/insightfinder"
      version = "{terraform_version}"
    }}
  }}

  backend "s3" {{
    bucket         = "insightfinder-terraform-state"
    key            = "{key}"
    region         = "us-east-1"
    dynamodb_table = "insightfinder-terraform-locks"
    encrypt        = true
  }}
}}
'''


def _provider_tf() -> str:
    return '''\
provider "insightfinder" {
  base_url    = var.base_url
  username    = var.if_username
  license_key = var.if_licensekey
}
'''


def _system_variables_tf() -> str:
    return '''\
variable "if_username" {
  description = "InsightFinder account username"
  type        = string
}

variable "if_licensekey" {
  description = "InsightFinder license key"
  type        = string
  sensitive   = true
}

variable "base_url" {
  description = "Base URL of the InsightFinder instance"
  type        = string
}

variable "system_name" {
  description = "InsightFinder system name this workspace manages"
  type        = string
}

variable "servicenow_host" {
  description = "ServiceNow host url"
  type        = string
  default     = ""
}

variable "servicenow_username" {
  description = "ServiceNow service account username"
  type        = string
  default     = ""
}

variable "servicenow_password" {
  description = "ServiceNow service account password"
  type        = string
  sensitive   = true
  default     = ""
}

variable "servicenow_clientid" {
  description = "ServiceNow service account clientId"
  type        = string
  sensitive   = true
  default     = ""
}

variable "servicenow_clientsecret" {
  description = "ServiceNow service account clientSecret"
  type        = string
  sensitive   = true
  default     = ""
}
'''


def _tfvars(base_url: str, system_name: str, servicenow_host: str = "") -> str:
    lines = [
        f"# All environment-specific values for {system_name}.",
        "# ⚠️  Sensitive values (credentials) are loaded from GitHub Secrets.",
        "#     See workflows for secret naming convention: <ENV>_<SYSTEM>_<VARNAME>",
        "",
        f'base_url    = "{base_url}"',
        f'system_name = "{system_name}"',
        "",
        "# InsightFinder credentials — loaded from secrets",
        "# if_username   = \"...\"  # Set via GitHub Secrets",
        "# if_licensekey = \"...\"  # Set via GitHub Secrets",
    ]
    if servicenow_host:
        lines += [
            "",
            "# ServiceNow connection details — passwords/secrets loaded from GitHub",
            f'servicenow_host = "{servicenow_host}"',
            "# servicenow_username     = \"...\"  # Set via GitHub Secrets",
            "# servicenow_password     = \"...\"  # Set via GitHub Secrets",
            "# servicenow_clientid     = \"...\"  # Set via GitHub Secrets",
            "# servicenow_clientsecret = \"...\"  # Set via GitHub Secrets",
        ]
    return "\n".join(lines) + "\n"


def _projects_tf(has_servicenow: bool) -> str:
    lines = [
        'module "projects" {',
        '  source = "./projects"',
        "",
        "  system_name = var.system_name",
    ]
    if has_servicenow:
        lines += [
            "",
            "  # ServiceNow credentials",
            "  servicenow_host         = var.servicenow_host",
            "  servicenow_username     = var.servicenow_username",
            "  servicenow_password     = var.servicenow_password",
            "  servicenow_clientid     = var.servicenow_clientid",
            "  servicenow_clientsecret = var.servicenow_clientsecret",
        ]
    lines += [
        "",
        "  providers = {",
        "    insightfinder = insightfinder",
        "  }",
        "}",
        "",
    ]
    return "\n".join(lines)


def _projects_variables_tf(has_servicenow: bool) -> str:
    lines = [
        'variable "system_name" {',
        '  description = "System name passed from parent module"',
        "  type        = string",
        "}",
    ]
    if has_servicenow:
        lines += [
            "",
            'variable "servicenow_host" {',
            '  description = "ServiceNow host url"',
            "  type        = string",
            "}",
            "",
            'variable "servicenow_username" {',
            '  description = "ServiceNow service account username"',
            "  type        = string",
            "}",
            "",
            'variable "servicenow_password" {',
            '  description = "ServiceNow service account password"',
            "  type        = string",
            "  sensitive   = true",
            "}",
            "",
            'variable "servicenow_clientid" {',
            '  description = "ServiceNow service account clientId"',
            "  type        = string",
            "  sensitive   = true",
            "}",
            "",
            'variable "servicenow_clientsecret" {',
            '  description = "ServiceNow service account clientSecret"',
            "  type        = string",
            "  sensitive   = true",
            "}",
        ]
    return "\n".join(lines) + "\n"


def _projects_versions_tf() -> str:
    """Child module versions.tf — no version lock, inherited from root."""
    return '''\
terraform {
  required_providers {
    insightfinder = {
      source = "insightfinder/insightfinder"
    }
  }
}
'''


def generate_project_tf(project_name: str, project_data: Dict,
                        system_name: str, is_servicenow_project: bool) -> str:
    """Generate a single project's .tf content for use inside the module."""

    # --- Parse settings ---
    settings_raw = project_data.get("settings") or {}
    settings_data: Dict[str, Any] = {}
    if "settingList" in settings_raw:
        for _key, settings_str in settings_raw["settingList"].items():
            try:
                settings_data = parse_project_settings(settings_str)
            except Exception:
                pass
            break

    keywords_data = project_data.get("keywords") or {}

    summary_meta = project_data.get("summary") or {}
    summary_settings: List[str] = summary_meta.get("summarySetting", [])
    metafield_settings: List[str] = summary_meta.get("metaFieldSetting", [])
    dampening_field_settings: List[str] = summary_meta.get("dampeningFieldSetting", [])

    jsonkeys_raw = project_data.get("jsonkeys") or {}
    if isinstance(jsonkeys_raw, list):
        json_keys_data = jsonkeys_raw
    else:
        json_keys_data = jsonkeys_raw.get("jsonKeyList", [])

    servicenow_data = project_data.get("servicenow") if is_servicenow_project else None

    # --- Build HCL ---
    resource_name = tf_resource_name(project_name)
    cfg: List[str] = []

    cfg.append(f'resource "insightfinder_project" "{resource_name}" {{')
    cfg.append(f'  project_name = "{project_name}"')
    cfg.append(f'  system_name  = var.system_name')
    cfg.append('')

    # project_creation_config
    cfg.append('  project_creation_config = {')
    if is_servicenow_project:
        cfg.append('    data_type          = "Log"')
        cfg.append('    instance_type      = "ServiceNow"')
        cfg.append('    project_cloud_type = "ServiceNow"')
        cfg.append('    insight_agent_type = "Custom"')
        # The servicenow_table needs a real value; use data from settings or placeholder
        sn_table = (servicenow_data or {}).get("servicenow_table", "incident")
        cfg.append(f'    servicenow_table   = "{sn_table}"')
    else:
        cfg.append('    data_type          = "Log"')
        cfg.append('    instance_type      = "OnPremise"')
        cfg.append('    project_cloud_type = "OnPremise"')
        cfg.append('    insight_agent_type = "Historical"')
    cfg.append('  }')
    cfg.append('')

    # All mapped settings attributes
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

    for api_key, tf_key in attribute_mapping.items():
        if api_key in settings_data:
            value = settings_data[api_key]
            if api_key == 'emailSetting' and isinstance(value, dict):
                if 'awSeverityLevel' not in value:
                    value = dict(value)
                    value['awSeverityLevel'] = 'Major'
            cfg.append(f'  {tf_key} = {format_terraform_value(value)}')

    # ServiceNow block using var references for credentials
    if is_servicenow_project:
        cfg.append('')
        cfg.append('  # ServiceNow third-party settings')
        cfg.append('  project_servicenow_settings = {')
        sn = servicenow_data or {}
        cfg.append(f'    host                 = var.servicenow_host')
        cfg.append(f'    servicenow_user      = var.servicenow_username')
        cfg.append(f'    servicenow_password  = var.servicenow_password')
        cfg.append(f'    client_id            = var.servicenow_clientid')
        cfg.append(f'    client_secret        = var.servicenow_clientsecret')
        cfg.append(f'    instance_field       = "{sn.get("instanceField", "")}"')
        cfg.append(f'    instance_field_regex = "{sn.get("instanceFieldRegex", "")}"')
        cfg.append(f'    timestamp_format     = "{sn.get("timestampFormat", "")}"')
        cfg.append(f'    sysparm_query        = "{sn.get("sysparmQuery", "")}"')
        cfg.append(f'    proxy                = "{sn.get("proxy", "")}"')
        fields_json = json.dumps(sn.get('additionalFields', {}))
        cfg.append(f'    additional_fields    = {fields_json}')
        cfg.append('  }')

    # log_label_settings
    log_labels = convert_keywords_to_log_labels(keywords_data)
    if log_labels:
        cfg.append('')
        cfg.append('  log_label_settings = [')
        for i, label in enumerate(log_labels):
            cfg.append('    {')
            cfg.append(f'      label_type       = "{label["label_type"]}",')
            cfg.append(f'      log_label_string = jsonencode({json.dumps(label["log_label_string"])})')
            if i < len(log_labels) - 1:
                cfg.append('    },')
            else:
                cfg.append('    }')
        cfg.append('  ]')

    # json_key_settings
    json_key_settings = convert_json_keys_to_terraform(
        json_keys_data,
        summary_settings=summary_settings,
        metafield_settings=metafield_settings,
        dampening_field_settings=dampening_field_settings,
    )
    if json_key_settings:
        cfg.append('')
        cfg.append('  json_key_settings = [')
        for i, ks in enumerate(json_key_settings):
            cfg.append('    {')
            cfg.append(f'      json_key                = "{ks["json_key"]}"')
            cfg.append(f'      type                    = "{ks["type"]}"')
            cfg.append(f'      summary_setting         = {format_terraform_value(ks["summary_setting"])}')
            cfg.append(f'      metafield_setting       = {format_terraform_value(ks["metafield_setting"])}')
            cfg.append(f'      dampening_field_setting = {format_terraform_value(ks["dampening_field_setting"])}')
            if i < len(json_key_settings) - 1:
                cfg.append('    },')
            else:
                cfg.append('    }')
        cfg.append('  ]')

    cfg.append('}')
    return '\n'.join(cfg)


# ---------------------------------------------------------------------------
# File writing helpers
# ---------------------------------------------------------------------------

def write_file(path: str, content: str, dry_run: bool = False) -> None:
    if dry_run:
        print(f"  [dry-run] Would write: {path}")
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)


# ---------------------------------------------------------------------------
# Main generation logic
# ---------------------------------------------------------------------------

def process_system(session: requests.Session, env_name: str, env_cfg: Dict,
                   system: Dict, output_dir: str, delay: float,
                   dry_run: bool,
                   allowed_projects: Optional[set] = None) -> Dict[str, int]:
    """Generate all Terraform files for one system. Returns stats.

    allowed_projects: if set, only process projects whose names are in this set.
                      None means process all projects (subject to type filter).
    """
    system_name = get_system_display_name(system)
    system_id = get_system_id(system)
    base_url = env_cfg["base_url"].rstrip('/')
    username = env_cfg["username"]
    api_key = env_cfg["licensekey"]
    terraform_version = str(env_cfg.get("terraform_version", ">= 1.6.1"))
    project_types: List[str] = env_cfg.get("project_types", env_cfg.get("project_type", []))
    if isinstance(project_types, str):
        project_types = [project_types]

    all_projects_raw = system.get("projectDetailsList", system.get("projectDetailList", []))
    if isinstance(all_projects_raw, str):
        try:
            all_projects = json.loads(all_projects_raw)
        except (json.JSONDecodeError, ValueError):
            all_projects = []
    else:
        all_projects = all_projects_raw or []
    projects = filter_projects_by_type(all_projects, project_types)

    # Apply only_process.projects filter if provided
    if allowed_projects is not None:
        projects = [p for p in projects
                    if (p.get("projectName") or p.get("name") or "") in allowed_projects]

    filter_desc = "type+project filter" if allowed_projects is not None else "type filter"
    print(f"\n  System: {system_name!r}  ({len(projects)}/{len(all_projects)} projects after {filter_desc})")

    if not projects:
        print("    No matching projects — skipping system.")
        return {"projects": 0, "skipped": 0}

    system_dir = os.path.join(output_dir, env_name, system_name)
    projects_dir = os.path.join(system_dir, "projects")

    # --- Fetch system-level settings ---
    print(f"    Fetching system-level settings (KB, notifications)...")
    kb_global, kb_incident, notifications = fetch_system_level_settings(
        session, base_url, username, api_key, username, system_id
    )

    # --- Determine if any project uses ServiceNow ---
    servicenow_projects = {
        p["projectName"] for p in projects
        if (p.get("cloudType") or "").lower() == "servicenow"
    }
    has_servicenow = len(servicenow_projects) > 0

    # Collect a representative SN host from project data (filled in later)
    sn_host_for_tfvars = ""

    # --- Write system-level files ---
    write_file(os.path.join(system_dir, "versions.tf"),
               _versions_tf(env_name, system_name, terraform_version), dry_run)
    write_file(os.path.join(system_dir, "provider.tf"),
               _provider_tf(), dry_run)
    write_file(os.path.join(system_dir, "variables.tf"),
               _system_variables_tf(), dry_run)
    write_file(os.path.join(system_dir, "projects.tf"),
               _projects_tf(has_servicenow), dry_run)

    # --- Write projects/ boilerplate ---
    write_file(os.path.join(projects_dir, "versions.tf"),
               _projects_versions_tf(), dry_run)
    write_file(os.path.join(projects_dir, "variables.tf"),
               _projects_variables_tf(has_servicenow), dry_run)

    # --- Write system_settings.tf in system folder (not projects/) ---
    has_sys_settings = kb_global or kb_incident or notifications
    if has_sys_settings:
        sys_settings_content = generate_system_settings_config(
            system_name=system_name,
            kb_global_data=kb_global,
            kb_incident_data=kb_incident,
            notifications_data=notifications,
            system_name_expr="var.system_name",
        )
        write_file(os.path.join(system_dir, "system_settings.tf"),
                   sys_settings_content + "\n", dry_run)

    # --- Generate per-project files ---
    generated = 0
    skipped = 0

    for proj in projects:
        project_name = proj.get("projectName") or proj.get("name") or ""
        if not project_name:
            skipped += 1
            continue

        is_sn = project_name in servicenow_projects
        print(f"    [{generated + skipped + 1}/{len(projects)}] {project_name}"
              + (" (ServiceNow)" if is_sn else ""))

        try:
            project_data = fetch_project_data(
                session, base_url, username, api_key, username, project_name
            )
        except Exception as e:
            print(f"      Error fetching data: {e}", file=sys.stderr)
            skipped += 1
            if delay > 0:
                time.sleep(delay)
            continue

        # Capture SN host from first SN project
        if is_sn and not sn_host_for_tfvars and project_data.get("servicenow"):
            sn_host_for_tfvars = project_data["servicenow"].get("host", "")

        try:
            tf_content = generate_project_tf(project_name, project_data,
                                             system_name, is_sn)
        except Exception as e:
            print(f"      Error generating TF: {e}", file=sys.stderr)
            skipped += 1
            if delay > 0:
                time.sleep(delay)
            continue

        tf_filename = tf_resource_name(project_name) + ".tf"
        write_file(os.path.join(projects_dir, tf_filename), tf_content + "\n", dry_run)
        generated += 1

        if delay > 0:
            time.sleep(delay)

    # --- Write terraform.tfvars (after we have SN host if any) ---
    write_file(os.path.join(system_dir, "terraform.tfvars"),
               _tfvars(base_url, system_name, sn_host_for_tfvars), dry_run)

    print(f"    Generated: {generated}  Skipped: {skipped}")
    return {"projects": generated, "skipped": skipped}


def run(config_path: str, output_dir: str, env_filter: Optional[str],
        dry_run: bool, no_ssl_verify: bool) -> None:
    cfg = load_config(config_path)

    global_delay = float(cfg.get("Delay", cfg.get("delay", 0)))
    session = make_session(no_ssl_verify)

    total_projects = 0
    total_skipped = 0
    total_systems = 0

    # Iterate environments (skip non-dict top-level keys like Delay)
    for env_name, env_cfg in cfg.items():
        if not isinstance(env_cfg, dict):
            continue
        if env_filter and env_name.upper() != env_filter.upper():
            continue

        print(f"\n{'='*60}")
        print(f"Environment: {env_name}  ({env_cfg.get('base_url', '')})")
        print(f"{'='*60}")

        username = env_cfg.get("username", "")
        api_key = env_cfg.get("licensekey", "")
        base_url = env_cfg.get("base_url", "").rstrip('/')

        if not username or not api_key or not base_url:
            print(f"  Skipping {env_name}: missing username/licensekey/base_url", file=sys.stderr)
            continue

        # Parse only_process filter
        only_process = env_cfg.get("only_process") or {}
        allowed_systems: set = set(only_process.get("systems") or [])
        extra_projects: set = set(only_process.get("projects") or [])
        has_filter = bool(allowed_systems or extra_projects)

        if has_filter:
            parts = []
            if allowed_systems:
                parts.append(f"systems={sorted(allowed_systems)}")
            if extra_projects:
                parts.append(f"projects={sorted(extra_projects)}")
            print(f"  only_process filter: {', '.join(parts)}")

        print(f"  Fetching owned systems for {username}...")
        systems = get_own_systems(session, base_url, username, api_key, username)
        print(f"  Found {len(systems)} owned system(s).")

        for system in systems:
            system_display = get_system_display_name(system)

            if has_filter:
                system_in_allowed = system_display in allowed_systems

                if system_in_allowed:
                    # Process all projects in this system (type filter still applies)
                    project_filter = None
                else:
                    # Check if any explicitly listed projects belong to this system
                    if not extra_projects:
                        print(f"\n  System: {system_display!r} — skipped (not in only_process.systems)")
                        continue
                    system_project_names = {
                        (p.get("projectName") or p.get("name") or "")
                        for p in (system.get("projectDetailsList")
                                  or system.get("projectDetailList") or [])
                        if isinstance(p, dict)
                    }
                    matching = extra_projects & system_project_names
                    if not matching:
                        print(f"\n  System: {system_display!r} — skipped (no matching projects)")
                        continue
                    project_filter = matching
            else:
                project_filter = None

            total_systems += 1
            stats = process_system(session, env_name, env_cfg, system,
                                   output_dir, global_delay, dry_run,
                                   allowed_projects=project_filter)
            total_projects += stats["projects"]
            total_skipped += stats["skipped"]

    print(f"\n{'='*60}")
    print(f"Done!  Environments: {env_filter or 'all'}  "
          f"Systems: {total_systems}  "
          f"Projects generated: {total_projects}  "
          f"Skipped: {total_skipped}")
    print(f"Output directory: {output_dir}")

    if not dry_run and total_projects > 0:
        print(f"\nRunning: terraform fmt -recursive {output_dir}")
        result = subprocess.run(["terraform", "fmt", "-recursive", output_dir])
        if result.returncode != 0:
            print("Warning: terraform fmt exited with non-zero status", file=sys.stderr)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Auto-generate Terraform files from InsightFinder API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--config", "-c", default="config.yaml",
                        help="Path to config.yaml (default: config.yaml)")
    parser.add_argument("--output-dir", "-o", default="TerraformFiles",
                        help="Root output directory (default: TerraformFiles)")
    parser.add_argument("--env", help="Only process this environment (e.g. NBC)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be written without creating files")
    parser.add_argument("--no-ssl-verify", action="store_true",
                        help="Disable SSL certificate verification")

    args = parser.parse_args()

    if not os.path.exists(args.config):
        print(f"Error: config file not found: {args.config}", file=sys.stderr)
        sys.exit(1)

    run(
        config_path=args.config,
        output_dir=args.output_dir,
        env_filter=args.env,
        dry_run=args.dry_run,
        no_ssl_verify=args.no_ssl_verify,
    )


if __name__ == "__main__":
    main()
