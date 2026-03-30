#!/usr/bin/env python3
"""
Elasticsearch LLM Agent

Queries dataset and prompt indexes from Elasticsearch and uploads them to InsightFinder.
Supports both Elasticsearch 7.x and 8.x Python clients, and both streaming (live)
and historical query modes.

Dataset schema expected in ES:
  { "content": "...", "dataset_name": "...", "@timestamp": "..." }

Prompt schema expected in ES:
  { "prompts": [{"prompt": "..."}, ...], "template_name": "...", "@timestamp": "..." }
"""

import configparser
import logging
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from typing import Optional

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Detect elasticsearch Python client major version (7 vs 8)
# ---------------------------------------------------------------------------
try:
    import elasticsearch as _es_module
    _ver = _es_module.__version__
    ES_CLIENT_VERSION = _ver[0] if isinstance(_ver, tuple) else int(_ver.split('.')[0])
except ImportError:
    logger.error(
        "The 'elasticsearch' package is not installed.\n"
        "For ES 7.x:  pip install 'elasticsearch>=7,<8'\n"
        "For ES 8.x:  pip install 'elasticsearch>=8'"
    )
    sys.exit(1)

from elasticsearch import Elasticsearch  # noqa: E402 (after version check)

CONFIG_FILE = os.path.join(os.path.dirname(__file__), 'conf.d', 'config.ini')


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def load_config(config_file: str) -> configparser.ConfigParser:
    config = configparser.ConfigParser()
    if not os.path.exists(config_file):
        logger.error(f"Config file not found: {config_file}")
        sys.exit(1)
    config.read(config_file)
    return config


def _strip(value: str) -> str:
    return (value or '').strip()


# ---------------------------------------------------------------------------
# Elasticsearch connection (supports 7.x and 8.x clients)
# ---------------------------------------------------------------------------

def get_es_connection(config: configparser.ConfigParser) -> Optional[Elasticsearch]:
    """
    Create an Elasticsearch client compatible with both the 7.x and 8.x Python
    client libraries.  The major version of the installed package determines
    which parameter names are used (http_auth vs basic_auth, etc.).
    """
    es_cfg = config['elasticsearch']
    uris       = [u.strip() for u in _strip(es_cfg.get('es_uris', 'http://localhost:9200')).split(',')]
    http_auth  = _strip(es_cfg.get('http_auth', ''))
    verify_certs = es_cfg.getboolean('verify_certs', False)
    ca_certs   = _strip(es_cfg.get('ca_certs', '')) or None
    client_cert = _strip(es_cfg.get('client_cert', '')) or None
    client_key  = _strip(es_cfg.get('client_key', '')) or None

    try:
        if ES_CLIENT_VERSION >= 8:
            # ES 8.x client — uses basic_auth, ssl_show_warn, etc.
            kwargs: dict = {'verify_certs': verify_certs}
            if http_auth:
                kwargs['basic_auth'] = tuple(http_auth.split(':', 1))
            if ca_certs:
                kwargs['ca_certs'] = ca_certs
            if client_cert:
                kwargs['client_cert'] = client_cert
            if client_key:
                kwargs['client_key'] = client_key
        else:
            # ES 7.x client — uses http_auth, use_ssl, etc.
            kwargs = {'verify_certs': verify_certs}
            if http_auth:
                kwargs['http_auth'] = http_auth
            if ca_certs:
                kwargs['ca_certs'] = ca_certs
            if client_cert:
                kwargs['client_cert'] = client_cert
            if client_key:
                kwargs['client_key'] = client_key
            if any(u.startswith('https://') for u in uris):
                kwargs['use_ssl'] = True

        client = Elasticsearch(uris, **kwargs)
        info = client.info()
        es_version = info.get('version', {}).get('number', 'unknown')
        logger.info(f"Connected to Elasticsearch {es_version} (Python client v{ES_CLIENT_VERSION})")
        return client
    except Exception as exc:
        logger.error(f"Failed to connect to Elasticsearch: {exc}")
        return None


# ---------------------------------------------------------------------------
# Elasticsearch querying (PIT + search_after pagination)
# ---------------------------------------------------------------------------

def _open_pit(es_client: Elasticsearch, index: str) -> Optional[str]:
    """Open a Point-in-Time session.  Available in ES 7.10+ and 8.x."""
    try:
        if ES_CLIENT_VERSION >= 8:
            resp = es_client.open_point_in_time(index=index, keep_alive='1m')
        else:
            resp = es_client.open_point_in_time(index=index, keep_alive='1m')
        return resp.get('id') or resp.get('pit_id')
    except Exception as exc:
        logger.warning(f"Could not open PIT for index '{index}': {exc}. Falling back to basic pagination.")
        return None


def _close_pit(es_client: Elasticsearch, pit_id: str):
    try:
        if ES_CLIENT_VERSION >= 8:
            es_client.close_point_in_time(id=pit_id)
        else:
            es_client.close_point_in_time(body={'id': pit_id})
    except Exception as exc:
        logger.warning(f"Could not close PIT: {exc}")


def _do_search(
    es_client: Elasticsearch,
    index: Optional[str],
    query: dict,
    size: int,
    sort: list,
    pit: Optional[dict],
    search_after: Optional[list],
) -> dict:
    """
    Execute an ES search in a way compatible with both 7.x and 8.x clients.
    When a PIT is active, *index* is omitted from the request (PIT binds it).
    """
    kwargs = {'query': query, 'size': size, 'sort': sort}
    if pit:
        kwargs['pit'] = pit
    if search_after:
        kwargs['search_after'] = search_after
    if index and not pit:
        kwargs['index'] = index
    return es_client.search(**kwargs)


def query_index(
    es_client: Elasticsearch,
    index: str,
    timestamp_field: str,
    start_epoch: float,
    end_epoch: float,
    chunk_size: int = 1000,
) -> list:
    """
    Query *index* for documents whose *timestamp_field* falls in
    [start_epoch, end_epoch) (epoch seconds).  Handles pagination via
    PIT + search_after when available, falling back to simple from/size.

    Returns a list of _source dicts, each augmented with '_id'.
    """
    results: list = []
    query = {
        'bool': {
            'must': [
                {
                    'range': {
                        timestamp_field: {
                            'format': 'epoch_second',
                            'gte': int(start_epoch),
                            'lt': int(end_epoch),
                        }
                    }
                }
            ]
        }
    }
    sort = [{timestamp_field: {'order': 'asc'}}]

    pit_id = _open_pit(es_client, index)
    pit    = {'id': pit_id, 'keep_alive': '1m'} if pit_id else None
    # When PIT is active the index is encoded in the PIT itself
    search_index = None if pit_id else index

    last_sort: Optional[list] = None
    page_from = 0

    while True:
        try:
            response = _do_search(
                es_client,
                search_index,
                query,
                chunk_size,
                sort,
                pit,
                last_sort if pit_id else None,
            )
        except Exception as exc:
            logger.error(f"Search error on index '{index}': {exc}")
            break

        if 'error' in response:
            logger.error(f"Elasticsearch returned error for index '{index}': {response['error']}")
            break

        hits = response.get('hits', {}).get('hits', [])
        if not hits:
            break

        for hit in hits:
            doc = hit.get('_source', {})
            doc['_id'] = hit.get('_id')
            results.append(doc)

        if len(hits) < chunk_size:
            break

        if pit_id:
            # Update PIT id and advance via search_after
            pit_id = response.get('pit_id', pit_id)
            pit['id'] = pit_id
            last_sort = hits[-1].get('sort')
        else:
            # Plain offset pagination fallback
            page_from += chunk_size
            sort_with_from = sort  # reuse sort; add 'from' in body via extra logic below
            # We cannot use search_after without PIT, so re-query with 'from'
            # Re-issue with updated from value — patch query inline
            try:
                if ES_CLIENT_VERSION >= 8:
                    kwargs2 = {
                        'query': query,
                        'size': chunk_size,
                        'sort': sort,
                        'from_': page_from,
                    }
                    if search_index:
                        kwargs2['index'] = search_index
                    response = es_client.search(**kwargs2)
                else:
                    body2 = {'query': query, 'size': chunk_size, 'sort': sort, 'from': page_from}
                    response = es_client.search(index=search_index, body=body2)
            except Exception as exc:
                logger.error(f"Pagination error on index '{index}': {exc}")
                break

            hits = response.get('hits', {}).get('hits', [])
            if not hits:
                break
            for hit in hits:
                doc = hit.get('_source', {})
                doc['_id'] = hit.get('_id')
                results.append(doc)
            if len(hits) < chunk_size:
                break

    if pit_id:
        _close_pit(es_client, pit_id)

    logger.info(f"Retrieved {len(results)} document(s) from index '{index}'")
    return results


# ---------------------------------------------------------------------------
# Field extraction helper
# ---------------------------------------------------------------------------

def get_field(doc: dict, field_path: str):
    """Extract a value from a nested dict using dot-separated field path."""
    current = doc
    for part in field_path.split('.'):
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


# ---------------------------------------------------------------------------
# InsightFinder API helpers
# ---------------------------------------------------------------------------

def _if_headers(api_key: str, user_name: str) -> dict:
    return {'X-Api-Key': api_key, 'X-User-Name': user_name}


def if_get_all_datasets(if_url: str, api_key: str, user_name: str) -> dict:
    """
    Fetch all datasets from InsightFinder.
    Returns a dict of {dataset_name: dataset_id}.
    Handles pagination automatically.
    """
    url = f"{if_url}/api/external/v1/llm-lab/datasets/search"
    datasets = {}
    page = 0
    page_size = 100
    while True:
        params = {'pageNumber': page, 'pageSize': page_size}
        try:
            response = requests.get(url, headers=_if_headers(api_key, user_name), params=params, timeout=15)
            response.raise_for_status()
            content = response.json().get('content', [])
            for item in content:
                datasets[item['datasetName']] = item['id']
            if len(content) < page_size:
                break
            page += 1
        except Exception as exc:
            logger.warning(f"Could not fetch datasets from InsightFinder: {exc}")
            break
    logger.info(f"Fetched {len(datasets)} dataset(s) from InsightFinder.")
    return datasets


def convert_prompt_with_dataset(prompt: str, dataset_id: str, dataset_name: str) -> str:
    """Replace {{dataset_name}} placeholder with the InsightFinder dataset tag."""
    dataset_tag = f'<dataset id="{dataset_id}"> {dataset_name} </dataset>'
    return prompt.replace(f"{{{{{dataset_name}}}}}", dataset_tag)


def if_dataset_exists(if_url: str, api_key: str, user_name: str, dataset_name: str) -> bool:
    """Return True if a dataset with exactly this name already exists in InsightFinder."""
    url = f"{if_url}/api/external/v1/llm-lab/datasets/search"
    params = {'datasetName': dataset_name, 'pageNumber': 0, 'pageSize': 100}
    try:
        response = requests.get(url, headers=_if_headers(api_key, user_name), params=params, timeout=15)
        response.raise_for_status()
        return any(
            item.get('datasetName') == dataset_name
            for item in response.json().get('content', [])
        )
    except Exception as exc:
        logger.warning(f"Could not check dataset existence for '{dataset_name}': {exc}")
        return False


def if_prompt_template_exists(if_url: str, api_key: str, user_name: str, template_name: str) -> bool:
    """Return True if a prompt template with exactly this name already exists in InsightFinder."""
    url = f"{if_url}/api/external/v2/prompt-templates/by-template-name"
    params = {'userName': user_name, 'templateName': template_name}
    try:
        response = requests.get(url, headers=_if_headers(api_key, user_name), params=params, timeout=15)
        response.raise_for_status()
        return any(
            item.get('key', {}).get('templateName') == template_name
            for item in response.json()
        )
    except Exception as exc:
        logger.warning(f"Could not check prompt template existence for '{template_name}': {exc}")
        return False


def if_create_dataset(
    if_url: str,
    api_key: str,
    user_name: str,
    dataset_name: str,
    content: str,
) -> Optional[str]:
    """
    Upload *content* as a text file to create a new dataset in InsightFinder.
    Returns the new dataset ID, or None on failure.
    """
    url = f"{if_url}/api/external/v1/llm-lab/datasets"
    params = {'datasetName': dataset_name}
    tmp_fd, tmp_path = tempfile.mkstemp(suffix='.txt')
    try:
        with os.fdopen(tmp_fd, 'w') as fh:
            fh.write(content)
        with open(tmp_path, 'rb') as fh:
            response = requests.post(
                url,
                headers=_if_headers(api_key, user_name),
                params=params,
                files={'datasetFile': fh},
                timeout=60,
            )
        response.raise_for_status()
        dataset_id = response.json().get('id')
        logger.info(f"Created dataset '{dataset_name}' (id={dataset_id})")
        return dataset_id
    except Exception as exc:
        logger.error(f"Failed to create dataset '{dataset_name}': {exc}")
        return None
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def if_create_prompt_template(
    if_url: str,
    api_key: str,
    user_name: str,
    template_name: str,
    prompts: list,
) -> bool:
    """
    Create a prompt template in InsightFinder from a list of prompt strings.
    Returns True on success.
    """
    url = f"{if_url}/api/external/v2/prompt-templates/from-list"
    body = {'templateName': template_name, 'prompts': prompts}
    try:
        response = requests.post(
            url,
            headers=_if_headers(api_key, user_name),
            json=body,
            timeout=30,
        )
        response.raise_for_status()
        logger.info(f"Created prompt template '{template_name}' with {len(prompts)} prompt(s)")
        return True
    except Exception as exc:
        logger.error(f"Failed to create prompt template '{template_name}': {exc}")
        return False


# ---------------------------------------------------------------------------
# Dataset processing
# ---------------------------------------------------------------------------

def process_datasets(
    es_client: Elasticsearch,
    config: configparser.ConfigParser,
    start_epoch: float,
    end_epoch: float,
):
    """
    Query the dataset index and upload each document to InsightFinder as a dataset.
    Each ES document produces one dataset; its *content_field* becomes the file body.
    """
    es_cfg   = config['elasticsearch']
    ds_cfg   = config['dataset_index']
    if_cfg   = config['insightfinder']

    index              = _strip(ds_cfg.get('index', 'test-dataset'))
    content_field      = _strip(ds_cfg.get('content_field', 'content'))
    dataset_name_field = _strip(ds_cfg.get('dataset_name_field', 'dataset_name'))
    default_name       = _strip(ds_cfg.get('default_dataset_name', 'default-dataset'))
    timestamp_field    = _strip(es_cfg.get('timestamp_field', '@timestamp'))
    chunk_size         = int(_strip(es_cfg.get('query_chunk_size', '1000')) or '1000')

    if_url    = _strip(if_cfg.get('if_url', '')).rstrip('/')
    api_key   = _strip(if_cfg.get('api_key', ''))
    user_name = _strip(if_cfg.get('user_name', ''))

    docs = query_index(es_client, index, timestamp_field, start_epoch, end_epoch, chunk_size)
    if not docs:
        logger.info("No dataset documents found in the queried time range.")
        return

    for doc in docs:
        content      = get_field(doc, content_field)
        dataset_name = get_field(doc, dataset_name_field) or default_name

        if not content:
            logger.warning(
                f"Document '{doc.get('_id')}' is missing field '{content_field}' — skipping."
            )
            continue

        if if_dataset_exists(if_url, api_key, user_name, dataset_name):
            logger.info(f"Dataset '{dataset_name}' already exists in InsightFinder, skipping.")
            continue

        if_create_dataset(if_url, api_key, user_name, dataset_name, str(content))


# ---------------------------------------------------------------------------
# Prompt processing
# ---------------------------------------------------------------------------

def process_prompts(
    es_client: Elasticsearch,
    config: configparser.ConfigParser,
    start_epoch: float,
    end_epoch: float,
):
    """
    Query the prompt index and upload each document to InsightFinder as a prompt
    template.  The *prompts_field* must be a list of objects; each object's
    *prompt_content_field* is extracted and the full list is sent together as
    a single template (matching the behaviour in main.py).
    """
    es_cfg  = config['elasticsearch']
    pr_cfg  = config['prompt_index']
    if_cfg  = config['insightfinder']

    index                = _strip(pr_cfg.get('index', 'test-prompt'))
    prompts_field        = _strip(pr_cfg.get('prompts_field', 'prompts'))
    prompt_content_field = _strip(pr_cfg.get('prompt_content_field', 'prompt'))
    template_name_field  = _strip(pr_cfg.get('template_name_field', 'template_name'))
    default_name         = _strip(pr_cfg.get('default_template_name', 'default-template'))
    timestamp_field      = _strip(es_cfg.get('timestamp_field', '@timestamp'))
    chunk_size           = int(_strip(es_cfg.get('query_chunk_size', '1000')) or '1000')

    if_url    = _strip(if_cfg.get('if_url', '')).rstrip('/')
    api_key   = _strip(if_cfg.get('api_key', ''))
    user_name = _strip(if_cfg.get('user_name', ''))

    docs = query_index(es_client, index, timestamp_field, start_epoch, end_epoch, chunk_size)
    if not docs:
        logger.info("No prompt documents found in the queried time range.")
        return

    # Fetch all datasets once so we can resolve {{dataset-name}} placeholders in prompts
    dataset_map = if_get_all_datasets(if_url, api_key, user_name)

    for doc in docs:
        template_name    = get_field(doc, template_name_field) or default_name
        raw_prompts_list = get_field(doc, prompts_field)

        if not isinstance(raw_prompts_list, list) or not raw_prompts_list:
            logger.warning(
                f"Document '{doc.get('_id')}' has missing or non-list '{prompts_field}' — skipping."
            )
            continue

        # Extract text from each item in the prompts array
        prompts: list[str] = []
        for item in raw_prompts_list:
            if isinstance(item, dict):
                text = item.get(prompt_content_field, '')
            elif isinstance(item, str):
                text = item
            else:
                text = str(item)
            if text:
                prompts.append(text)

        if not prompts:
            logger.warning(
                f"Document '{doc.get('_id')}' produced an empty prompts list — skipping."
            )
            continue

        # Replace any {{dataset-name}} placeholders with their InsightFinder dataset tags.
        # Each prompt is passed through every known dataset so multiple placeholders are resolved.
        converted: list[str] = []
        for p in prompts:
            for name, did in dataset_map.items():
                p = convert_prompt_with_dataset(p, did, name)
            converted.append(p)
        prompts = converted

        if if_prompt_template_exists(if_url, api_key, user_name, template_name):
            logger.info(f"Prompt template '{template_name}' already exists in InsightFinder, skipping.")
            continue

        if_create_prompt_template(if_url, api_key, user_name, template_name, prompts)


# ---------------------------------------------------------------------------
# Time parsing
# ---------------------------------------------------------------------------

def parse_datetime(s: str) -> float:
    """Parse a datetime string to epoch seconds (UTC assumed)."""
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d'):
        try:
            dt = datetime.strptime(s.strip(), fmt)
            return dt.replace(tzinfo=timezone.utc).timestamp()
        except ValueError:
            continue
    raise ValueError(f"Cannot parse datetime string: {s!r}")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run(config: configparser.ConfigParser):
    es_cfg = config['elasticsearch']
    if_cfg = config['insightfinder']

    his_time_range             = _strip(es_cfg.get('his_time_range', ''))
    query_time_offset_seconds  = int(_strip(es_cfg.get('query_time_offset_seconds', '0')) or '0')
    lookback_seconds           = int(_strip(es_cfg.get('streaming_lookback_seconds', '60')) or '60')

    es_client = get_es_connection(config)
    if not es_client:
        logger.error("Cannot proceed — Elasticsearch connection failed.")
        sys.exit(1)

    if his_time_range:
        # ------------------------------------------------------------------
        # Historical (replay) mode
        # ------------------------------------------------------------------
        parts = [p.strip() for p in his_time_range.split(',')]
        if len(parts) != 2:
            logger.error(
                f"Invalid his_time_range: {his_time_range!r}. "
                "Expected format: 'YYYY-MM-DD HH:MM:SS,YYYY-MM-DD HH:MM:SS'"
            )
            sys.exit(1)
        start_epoch = parse_datetime(parts[0])
        end_epoch   = parse_datetime(parts[1])
        logger.info(f"[Historical] Querying {parts[0]} → {parts[1]}")
        process_datasets(es_client, config, start_epoch, end_epoch)
        process_prompts(es_client, config, start_epoch, end_epoch)
    else:
        # ------------------------------------------------------------------
        # Streaming (live) mode — query the last N seconds of data
        # ------------------------------------------------------------------
        now         = time.time()
        end_epoch   = now - query_time_offset_seconds
        start_epoch = end_epoch - lookback_seconds

        logger.info(
            f"[Streaming] Querying last {lookback_seconds}s: "
            f"{datetime.fromtimestamp(start_epoch, tz=timezone.utc).isoformat()} → "
            f"{datetime.fromtimestamp(end_epoch, tz=timezone.utc).isoformat()}"
        )
        process_datasets(es_client, config, start_epoch, end_epoch)
        process_prompts(es_client, config, start_epoch, end_epoch)


def main():
    config = load_config(CONFIG_FILE)
    run(config)


if __name__ == '__main__':
    main()
