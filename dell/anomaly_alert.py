import configparser
from datetime import datetime, date, timedelta, timezone, time as datetime_time
import json
import logging
import pickle
import requests
import time


logging.basicConfig(level=logging.DEBUG,
                    format=('%(asctime)-15s'
                            '%(filename)s: '
                            '%(levelname)s: '
                            '%(funcName)s(): '
                            '%(lineno)d:\t'
                            '%(message)s')
                        )


def get_anomaly_data(host, data):
    url = host + '/api/v2/projectanomalytransfer'
    logging.debug(f"{url} {data}")
    resp = requests.get(url, params=data, verify=False)
    assert resp.status_code == 200, "failed to get anomaly data!"
    result = {}
    try:
        result = resp.json()
    except Exception as e:
        logging.WARNING(e)
    return result


def get_anomaly_events(start, end, events_sent, host, projects, user, licenseKey):
    """ given start and end time, get anomaly events for a project """
    startTime = int(start.timestamp()*1000)
    endTime = int(end.timestamp()*1000)
    logging.debug(startTime)
    logging.debug(endTime)
    events = []

    for proj_name in projects:
        print("project:", proj_name)
        data = {"projectName": proj_name, "transferToProjectName": "dummy", "transferToCustomerName": "user",
                "startTime": startTime, "endTime": endTime, "licenseKey": licenseKey, "userName": user}

        anomaly_data = get_anomaly_data(host, data)
        if len(anomaly_data) == 0:
            continue

        for d in anomaly_data['DATA']['anomalyEventsList']:
            for e in json.loads(d['rootCauseJson'])['rootCauseDetailsArr']:
                instance = e.get('instanceId')
                metric = e.get('rootCauseMetric')
                for event_time in e.get('timePairArr'):
                    event_start = event_time.get('startTimestamp')
                    key = f"{instance}-{metric}"
                    if key not in events_sent:
                        events_sent.update({key: event_start})
                        event = f"""{metric} ({e.get('metricValue')}) is {e.get('pct')}% {e.get('direction')} \
    than normal at {instance}"""
                        events.append((instance, event))
                        logging.debug(f"add event:{instance} {event}")

    return events


def send_alert(instance, event, url):
    logging.debug(f"alert to {url}: {event}")

    try:
        data = {
            "fqdn": instance,
            "severity": 4,
            "message": event,
            "complete": "false"
        }

        resp = requests.post(url, json=data)
        logging.debug(f"resp code = {resp.status_code}")
    except Exception as e:
        logging.warning(e)


def main():
    today = datetime.combine(date.today(), datetime_time(), tzinfo=timezone.utc)
    tomorrow = today + timedelta(days=1)
    start_time = time.time()
    logging.info(f"check anomaly in {today}")

    events_sent = {}

    config = configparser.ConfigParser()
    projects = []
    interval = 24

    try:
        config.read('cfg.ini')
        report_url = config['DEFAULT']['report_url']
        host = config['DEFAULT']['host']
        projects = config['DEFAULT']['project'].split(',')
        user = config['DEFAULT']['user']
        licenseKey = config['DEFAULT']['licenseKey']
        interval = int(config['DEFAULT']['interval'])
    except Exception as e:
        logging.warning(e)

    try:
        f = open("events_records", "rb")
        events_sent.update(pickle.load(f))
        f.close()
    except:
        pass

    logging.debug(f"today total events: {len(events_sent)}")

    for instance, event in get_anomaly_events(today, tomorrow, events_sent, host, projects, user, licenseKey):
        send_alert(instance, event, report_url)

    # clean up records
    utc_now = datetime.utcnow().timestamp()
    for k, v in events_sent.items():
        if utc_now - v/1000 > interval * 3600:
            events_sent.pop(k)

    with open("events_records", "wb") as f:
        pickle.dump(events_sent, f)

    logging.info(f"done in {time.time()-start_time:8.3f} secs")

if __name__ == '__main__':
    main()
