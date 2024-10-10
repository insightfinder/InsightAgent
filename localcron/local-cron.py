#!/usr/bin/env python

import argparse
import calendar
import datetime
import requests
import sys
import time
from time import gmtime, strftime
from sets import Set


logfile = '/var/log/localcron.log'
logging = True

def logmsg(msg):
    if logging:
        print strftime("%Y-%m-%d %H:%M:%S", gmtime()) + " [" + op + "] " + msg + "\n"

def usage():
    print ''
    print '\tUsage: ./local-cron.py <action>'
    print ''
    print '\twhere the action must be one of the following:'
    print '\t\t - appforecast'
    print '\t\t - bootstrapcheckagent'
    print '\t\t - bootstrapchecknonagent'
    print '\t\t - collect'
    print '\t\t - cronfrequencyepisodemining'
    print '\t\t - detect'
    print '\t\t - eventsupport'
    print '\t\t - email'
    print '\t\t - updateeventssecond'
    print '\t\t - freeFormatParser'
    print '\t\t - loadAllEC2Data'
    print '\t\t - processrawdata'
    print '\t\t - trainmaster'
    print '\t\t - addlogmetadata'
    print '\t\t - rawdatapreprocess'
    print '\t\t - createglobalview'
    print '\t\t - createglobalviewsnapshot'
    print '\t\t - triggersyscallanalysis'
    print '\t\t - cronsecondintervaldetect'
    print '\t\t - cronlogtrainmaster'
    print '\t\t - cronlogforcedcollection'
    print '\t\t - cronlogcollection'
    print '\t\t - secondintervaltrainmaster'
    print '\t\t - rawdatasplit'
    print '\t\t - updateprojectinfo'
    print '\t\t - logfrequentsequencedetection'
    print '\t\t - appbehaviorstats'
    print '\t\t - crondelete'
    print '\t\t - updateinstanceaddremovesecond'
    print '\t\t - updateinstanceaddremove'
    print '\t\t - cronfrequencyminingupdate'
    print '\t\t - checkqueuestatus'
    print '\t\t - logdetect'
    print '\t\t - cronpredictionerrorcalculation'
    print '\t\t - aggregatemetricdata'
    print '\t\t - cleanUpChunks'
    print '\t\t - cleanresultcache'
    print '\t\t - liveappforecast'
    print '\t\t - logsendsplunk'
    print '\t\t - detectfixedincidents'
    print '\t\t - cronretention'
    print '\t\t - croneventflush'
    print '\t\t - healthviewexport'
    print '\t\t - relationpreprocess'
    print '\t\t - predictedincidentalert'
    print '\t\t - cleanusertoken'
    print '\t\t - rootcauseanalysis'
    print '\t\t - insightSummary'
    print '\t\t - metricPrediction'
    print '\t\t - kpiliveprediction'
    print '\t\t - kpiprediction'
    print '\t\t - logcommonpattern'
    print '\t\t - logcollectdata'
    print '\t\t - incidentpredictiontimeline'
    print '\t\t - croncollectpredictionstats'
    print '\t\t - incidentalert'
    print '\t\t - baseline'
    print '\t\t - webhookalert'
    print '\t\t - updatemetricsettingandinstancemetadata'
    print '\t\t - logfeatureoutliermodel'
    print '\t\t - logmissingdataalert'
    print '\t\t - lograwdataflush'
    print '\t\t - insightsreport'
    print '\t\t - logtometricflush'
    print '\t\t - logupdatecalendar'
    print '\t\t - anomalytransfer'
    print '\t\t - logcommoneventdataclean'
    print '\t\t - systemdown'
    print '\t\t - logeventfrequencyflush'
    print '\t\t - logfrequencydetectiondata'
    print '\t\t - loggooglepubsub'
    print '\t\t - refresh-teams-tokens'
    print '\t\t - long-termincident-predictiontimeline'
    print '\t\t - checkdeletedincident'
    print '\t\t - systemstructure'
    print '\t\t - metricoverviewstatus'
    print '\t\t - metricprovision'
    print '\t\t - systemautoshare'
    print '\t\t - detectedincidentalert'
    print '\t\t - knowledgebase-prediction'
    print '\t\t - insightsweeklyreport'
    print '\t\t - awsmpnotification'
    print '\t\t - validate-down-incident'
    print '\n'

ops = Set(['appforecast',
           'bootstrapcheckagent',
           'bootstrapchecknonagent',
           'collect',
           'cronfrequencyepisodemining',
           'detect',
           'eventsupport',
           'email',
           'updateeventssecond',
           'rawdatapreprocess',
           'freeFormatParser',
           'loadAllEC2Data'
           'processrawdata',
           'trainmaster',
           'createglobalview',
           'createglobalviewsnapshot',
           'addlogmetadata',
           'secondintervaltrainmaster',
           'logfrequentsequencedetection',
           'rawdatasplit',
           'cronlogtrainmaster',
           'cronsecondintervaldetect',
           'triggersyscallanalysis',
           'updateprojectinfo',
           'crondelete',
           'appbehaviorstats',
           'cronlogcollection',
           'cronlogforcedcollection',
           'updateinstanceaddremovesecond',
           'updateinstanceaddremove',
           'cronfrequencyminingupdate',
           'checkqueuestatus',
           'logdetect',
           'croneventflush',
           'cronpredictionerrorcalculation',
           'aggregatemetricdata',
           'cleanUpChunks',
           'cleanresultcache',
           'liveappforecast',
           'logsendsplunk',
           'detectfixedincidents',
           'cronretention',
           'healthviewexport',
           'relationpreprocess',
           'predictedincidentalert',
           'cleanusertoken',
           'rootcauseanalysis',
           'insightSummary',
           'metricPrediction',
           'kpiliveprediction',
           'kpiprediction',
           'logcommonpattern',
           'logcollectdata',
           'incidentpredictiontimeline',
           'croncollectpredictionstats',
           'incidentalert',
           'baseline',
           'webhookalert',
           'updatemetricsettingandinstancemetadata',
           'logfeatureoutliermodel',
           'logmissingdataalert',
           'lograwdataflush',
           'insightsreport',
           'logtometricflush',
           'logupdatecalendar',
           'anomalytransfer',
           'logcommoneventdataclean',
           'systemdown',
           'logeventfrequencyflush',
           'logfrequencydetectiondata',
           'loggooglepubsub',
           'refresh-teams-tokens',
           'long-term-incidentpredictiontimeline',
           'checkdeletedincident',
           'systemstructure',
           'metricoverviewstatus',
           'metricprovision',
           'systemautoshare',
           'detectedincidentalert',
           'knowledgebase-prediction',
           'insightsweeklyreport',
           'awsmpnotification',
           'validate-down-incident',
           '*'
           ])

def send_request(url, retry, wait, deadline):
    for i in range(0, retry):
        wait = wait * (1.5 ** i)
        try:
            r = requests.post(url, verify=False)
            if r.ok:
                logmsg("Succeeded:" + url)
                return r
            else:
                logmsg("Failed(response):" + url)
                time.sleep(wait)
        except requests.exceptions.RequestException as e:
            logmsg(str(e))
            time.sleep(wait)

        if datetime.datetime.now() >= deadline:
            logmsg("Failed(deadline):" + url)
            sys.exit(1)
        if i == retry - 1:
            logmsg("Failed(retry):" + url)
            sys.exit(1)


parser = argparse.ArgumentParser()
parser.add_argument('operation', help='operation')
parser.add_argument('-p', '--parameters', nargs='+', help='operation parameters')
parser.add_argument('-f', '--frequency', type=int, required=True, help='cron job frequency')
parser.add_argument('-r', '--retry', default=5, type=int, help='max retry to send request (default 5)')
parser.add_argument('-w', '--wait', default=60, type=int, help='wait seconds between retry (default 60)')
parser.add_argument('-u', '--url', default="https://insightfinder-appserver", help='url of appserver')
args = parser.parse_args()

op = args.operation
if op not in ops:
    logmsg("Invalid operation attempted")
    usage()
    quit()

freq = args.frequency
op_params = "?" + '&'.join(args.parameters) if args.parameters is not None else ''
op_url = args.url + '/localcron/' + args.operation + op_params
status_params = '?operation=' + op + '&frequency=' + str(freq) + \
                '&updatetimestamp=' + str(calendar.timegm(gmtime()) * 1000)
status_url = args.url + '/api/v1/cronstatus' + status_params

retry = args.retry if freq >= 600 else 1
wait = args.wait
deadline = datetime.datetime.now() + datetime.timedelta(seconds=freq)

for url in [op_url, status_url]:
    send_request(url, retry, wait, deadline)
