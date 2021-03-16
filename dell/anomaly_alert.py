import requests
import time
import json
import pendulum
import pickle
import logging
import configparser


logging.basicConfig(level=logging.WARNING)


def log_in(host, user_name, password, user_agent):
    TOKEN = "token"
    USER_AGENT = "User-Agent"
    X_CSRF_TOKEN = "X-CSRF-Token"
    url = host + '/api/v1/login-check'
    headers = {"User-Agent": user_agent}
    data = {"userName":user_name, "password":password}
    resp = requests.post(url, data=data, headers=headers, verify=False)
    assert resp.status_code == 200, "failed to login!"
    logging.debug("Successfully login and get the token")
    headers = {USER_AGENT: user_agent, X_CSRF_TOKEN: json.loads(resp.text)[TOKEN]}
    return resp.cookies, headers


def get_anomaly_data(host, data):
    url = host + '/api/v2/projectanomalytransfer'
    logging.debug(f"{url} {data}")
    resp = requests.get(url, params=data, verify=False)
    logging.debug(str(resp))
    assert resp.status_code == 200, "failed to get anomaly data!"
    return json.loads(resp.text)


def get_anomaly_events(start, end, events_sent, host, profile, licenseKey):
    startTime = int(start.timestamp()*1000)
    endTime = int(end.timestamp()*1000)

    proj_name, user_name = profile.split('@')

    data = {"projectName": proj_name, "transferToProjectName": "dummy", "transferToCustomerName": "user",
            "startTime": startTime, "endTime": endTime, "licenseKey": licenseKey}
    user_agent = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/80.0.3987.122 Safari/537.36"

    # (cookies, headers) = log_in(host, user_name, password, user_agent)
    # cookies = dict(userName=user_name)
    data.update({"userName": user_name})
    # headers = {"User-Agent": user_agent}
    anomaly_data = get_anomaly_data(host, data)

    events = []
    for d in anomaly_data['DATA']['anomalyEventsList']:
        for e in json.loads(d['rootCauseJson'])['rootCauseDetailsArr']:
            # logging.debug(e)
            instance = e.get('instanceId')
            metric = e.get('rootCauseMetric')
            for event_time in e.get('timePairArr'):
                event_start = str(event_time.get('startTimestamp'))
                key = f"{instance}-{metric}-{event_start}"
                if key not in events_sent.get(start, ''):
                    logging.debug(f"events:{events_sent} {start} {key}")
                    events_sent[start].add(key)
                    event = f"""{metric} ({e.get('metricValue')}) is {e.get('pct')}% {e.get('direction')} \
than normal at {instance}"""
                    logging.debug(event)
                    events.append((instance, event))

    return events


def send_alert(instance, event, url):
    logging.debug(f"alert to {url}: {event}")
    try:
        data = {
            "fqdn": instance,
            "severity": 3,
            "message": event,
            "complete": "false"
        }

        resp = requests.post(url, json=data)
    except Exception:
        pass


def main():

    today = pendulum.today()
    tomorrow = pendulum.tomorrow()
    logging.info(f"started at {pendulum.now()}")

    events_sent = {today:set()}

    config = configparser.ConfigParser()
    try:
        config.read('cfg.ini')
        report_url = config['DEFAULT']['report_url']
        host = config['DEFAULT']['host']
        profile = config['DEFAULT']['profile']
        # password = config['DEFAULT']['password']
        licenseKey = config['DEFAULT']['licenseKey']
    except Exception as e:
        logging.warning(e)

    try:
        f = open("events_records", "rb")
        events_sent.update(pickle.load(f))
        f.close()
    except:
        pass

    logging.debug(f"today total events: {len(events_sent.get(today, ''))}")

    for instance, event in get_anomaly_events(today, tomorrow, events_sent, host, profile, licenseKey):
        send_alert(instance, event, report_url)

    # clean up records
    if len(events_sent) > 1:
        for day in events_sent.keys():
            if (today - day).hours >=24:
                events_sent.pop(day)

    with open("events_records", "wb") as f:
        pickle.dump(events_sent, f)

if __name__ == '__main__':
    main()