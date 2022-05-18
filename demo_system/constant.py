IF = "IF"
LICENSE_KEY = "license_key"
USER_NAME = "user_name"
SERVER_URL = "server_url"
START_TIME = "start_time"
NORMAL_TIME = "normal_time"
ABNORMAL_TIME = "abnormal_time"
PROJECT_NAME = "project_name"
DATA_TYPE = "data_type"
TIME_ZONE = "time_zone"
ACTION_TRIGGERED_MAP = "action_triggered_map"
REVERSE_DEPLOYMENT = "reverse_deployment"
LOG = "Log"
DEPLOYMENT = "Deployment"
WEB = "Web"
METRIC = "Metric"
ALERT = "Alert"
LOG_PROJECT_NAME = "TD-infrastructure-core"
DEPLOYMENT_PROJECT_NAME = "TD-deployment"
WEB_PROJECT_NAME = "TD-web"
METRIC_PROJECT_NAME = "TD-metric"
ALERT_PROJECT_NAME = "TD-alert"
DATA_TYPE_NORMAL = "normal"
DATA_TYPE_ABNORMAL = "abnormal"
DATE_TIME_FORMAT_MINUTE = "%Y-%m-%dT%H:%M:00"
DATE_TIME_FORMAT = "%Y-%m-%dT%H:%M:%S"
DATE_TIME_FORMAT_DAY = "%Y-%m-%d"

# Deployment data
DEPLOYMENT_DATA_BUGGY = [
'''jobType: DEPLOY\n
buildStatus: SUCCESS\n
gitLog: commit fee8238318dfe94d849604a8da7dff0bd59234d9\n
Merge: 2302b64a2 ef394aa82\n
Author: Tom <Tom@insightfinder.com>\n
    Merge pull request #5010 from DEMO/II-7100_checkout_service_feature\n
    Adding a new checkout service feature ''',
'''jobType: DEPLOY\n
buildStatus: SUCCESS\n
gitLog: commit 84403f9803894f08dedc1037a1462ae0ec4d3eb8\n
Merge: 2302b64a2 ef394aa82\n
Author: Tom <Tom@insightfinder.com>\n
    Merge pull request #5012 from DEMO/II-7100_checkout_service_feature\n
    Adding another checkout service feature ''']

DEPLOYMENT_DATA = [
'''jobType: DEPLOY\n
buildStatus: SUCCESS\n
gitLog: commit bdcf7eb22a9772f2d476940894064515b20fb145\n
Merge: 95fb86f 8d800832\n
Author: Peter <Peter@insightfinder.com>\n
    Merge pull request #5011 from DEMO/II-8000_fix_user_login_problem\n
    Fix the user login problem due to the null pointer exception
    Add try catch exception to avoid future exception''',
'''jobType: DEPLOY\n
buildStatus: SUCCESS\n
gitLog: commit 8d80083afce9e8b940719589b9ef9d8d2a602d3e\n
Merge: 0d7a465 503fca3\n
Author: Jack <Jack@insightfinder.com>\n
    Merge pull request #5013 from DEMO/II-8460_fix_database_connection_issue\n
    Database connection error
    Fix the misconfiguration
    Change the timeout setting''',
'''jobType: DEPLOY\n
buildStatus: SUCCESS\n
gitLog: commit 0d7a465e2631ac23546219bac4d686324cef218c\n
Merge: 2268422 6148138\n
Author: David <David@insightfinder.com>\n
    Merge pull request #5014 from DEMO/II-8489_add_setting_change_api\n
    Add the setting change api support
    Add new setting of user management''',
'''jobType: DEPLOY\n
buildStatus: SUCCESS\n
gitLog: commit 3bca2172b059166d42f15f9ec5bec839880722eb\n
Merge: 84403f9 a54095b\n
Author: Ariy <Ariy@insightfinder.com>\n
    Merge pull request #5015 from DEMO/II-6892_optimize_data_loading\n
    Add multithread support for data loading to enhance the performance
    Add paging support for loading large chunk of data''']

DEPLOYMENT_DATA_INDEX = {0:0, 4:0, 8:1, 12:1, 16:2, 20:3}

# Web data
WEB_INCIDENT_DATA = "Production 911: Checkout server returns 500 error"
WEB_NORMAL_DATA = ["User checked the dash board page", "User changed the profile setting", "User logged out",
                   "User logged in"]
WEB_USER = ["James", "Robert", "Mary", "Jennifer"]
WEB_API = ["api/v1/settingchange", "api/v1/checkout", "api/v1/shoppinglist", "api/v1/paymentupdate"]
WEB_ENV = ["NY", "WA", "NC"]
WEB_ERROR_CODE = [500, 504, 404, 400]
WEB_OK_CODE = 200

# Alert data
ALERT_INCIDENT_DATA = {"comments": "", "assignment group": "Software", "description": "", "close notes": "",
                       "configuration item": "", "priority": "1 - Critical", "caller": "Admin", "service": "",
                       "short description": "Production 911: Checkout server returns 500 error", "state": "In Progress",
                       "work notes": "cusomter cannot checkout", "assigned to": "Don Goodliffe"}

# Instance name for log
LOG_INSTANCE_LIST = ["84.206.252.176", "203.133.162.186", "248.23.23.69", "9.111.192.107", "249.148.28.81", "39.237.183.95",
                "102.38.146.196", "79.226.203.156", "141.87.7.150", "33.133.144.70"]
# Log data
NORMAL_LOG_DATA = ['''com.insightfinder.RabbitMQ.ConsumerTDLogStreaming processTask\nINFO: Start to process log data saving, ''',
'''com.insightfinder.RabbitMQ.ConsumerTDLogStreaming getPreprocessedRawDataMap\nINFO: Finish preprocessing for raw data''',
'''com.insightfinder.utility.ChunkingUtility getFinalRawEventArrayToSave\nINFO: Save events to buffer''',
'''com.insightfinder.logic.causal_relation_process.MultiHopDataProcessor findBestCausalGroup\nINFO: Get the best causal group candidate''',
'''com.insightfinder.logic.causal_relation_process.CausalMultiHopResultProcessor createLogResultList\nINFO: generating the src nodes and candidate log relation list''',
'''com.insightfinder.logic.MetricPredictionAnomalyProcessor doPredictionDetection\nWARNING: rawDataInfo.csvData is empty''',
'''com.insightfinder.RabbitMQ.ConsumerDetection processTask\nINFO: metric detection finished''',
'''com.insightfinder.models.payload.log.LogUpdateCalendarInfoPayload runTask\nINFO: Successfully to store the log calendar info''',
'''com.insightfinder.utility.LogCollectResultUtility updateNidMetadata\nINFO: Finish updating log nid time interval''',
'''com.insightfinder.utility.LogCollectResultUtility clusteringEvents\nINFO: Starting clustering events''']
NORMAL_EXCEPTION_DATA = ['''java.lang.ClassCastException: com.insightfinder.datastore.ActiveAWSProject cannot be cast to com.insightfinder.datastore.ActiveCustomProject
	at com.insightfinder.datastore.ActiveProject.getProjectFromCassandra(ActiveProject.java:329)
	at com.insightfinder.models.payload.DetectedIncidentAlertPayload.getDetectedIncidentAnomalyTimeLine(DetectedIncidentAlertPayload.java:109)
	at com.insightfinder.models.payload.DetectedIncidentAlertPayload.runTask(DetectedIncidentAlertPayload.java:94)
	at com.insightfinder.RabbitMQ.ConsumerDetectedIncidentAlert.processTask(ConsumerDetectedIncidentAlert.java:31)
	at com.insightfinder.RabbitMQ.IFARabbitmqConsumer.handleDelivery(IFARabbitmqConsumer.java:66)
	at com.rabbitmq.client.impl.ConsumerDispatcher$5.run(ConsumerDispatcher.java:149)
	at com.rabbitmq.client.impl.ConsumerWorkService$WorkPoolRunnable.run(ConsumerWorkService.java:104)
	at java.util.concurrent.ThreadPoolExecutor.runWorker(ThreadPoolExecutor.java:1149)
	at java.util.concurrent.ThreadPoolExecutor$Worker.run(ThreadPoolExecutor.java:624)
	at java.lang.Thread.run(Thread.java:748)''',
    '''com.insightfinder.exception.DataCorruptionException: Data Corruption
	at com.insightfinder.datastore.metric_data.InstanceMetricData$MetricMap.getMetricMap(InstanceMetricData.java:286)
	at com.insightfinder.datastore.metric_data.InstanceMetricData$TimestampMetricMap.getTimestampMetricMap(InstanceMetricData.java:261)
	at com.insightfinder.datastore.metric_data.aggregatedmetricdata.InstanceMetricDataAggregatedUtils.aggregateInstanceMetricDataByTimestamp(InstanceMetricDataAggregatedUtils.java:67)
	at com.insightfinder.RabbitMQ.ConsumerCronAggregateMetricData.handleDelivery(ConsumerCronAggregateMetricData.java:59)
	at com.rabbitmq.client.impl.ConsumerDispatcher$5.run(ConsumerDispatcher.java:149)
	at com.rabbitmq.client.impl.ConsumerWorkService$WorkPoolRunnable.run(ConsumerWorkService.java:104)
	at java.util.concurrent.ThreadPoolExecutor.runWorker(ThreadPoolExecutor.java:1149)
	at java.util.concurrent.ThreadPoolExecutor$Worker.run(ThreadPoolExecutor.java:624)
	at java.lang.Thread.run(Thread.java:748)''',
    '''com.datastax.driver.core.exceptions.InvalidQueryException: Some partition key parts are missing: instancename
	at com.datastax.driver.core.exceptions.InvalidQueryException.copy(InvalidQueryException.java:50)
	at com.datastax.driver.core.DriverThrowables.propagateCause(DriverThrowables.java:35)
	at com.datastax.driver.core.DefaultResultSetFuture.getUninterruptibly(DefaultResultSetFuture.java:293)
	at com.datastax.driver.core.AbstractSession.execute(AbstractSession.java:58)
	at com.datastax.driver.mapping.MappingSession.deleteByQuery(MappingSession.java:143)
	at com.insightfinder.datastore.CassandraStore.deleteByQuery(CassandraStore.java:496)
	at com.insightfinder.RabbitMQ.ConsumerCleanCron.cleanUpData(ConsumerCleanCron.java:67)
	at com.insightfinder.RabbitMQ.ConsumerCleanCron.processTask(ConsumerCleanCron.java:49)
	at com.insightfinder.RabbitMQ.IFARabbitmqConsumer.handleDelivery(IFARabbitmqConsumer.java:66)
	at com.rabbitmq.client.impl.ConsumerDispatcher$5.run(ConsumerDispatcher.java:149)
	at com.rabbitmq.client.impl.ConsumerWorkService$WorkPoolRunnable.run(ConsumerWorkService.java:104)
	at java.util.concurrent.ThreadPoolExecutor.runWorker(ThreadPoolExecutor.java:1149)
	at java.util.concurrent.ThreadPoolExecutor$Worker.run(ThreadPoolExecutor.java:624)
	at java.lang.Thread.run(Thread.java:748)''']
EXCEPTION_LOG_DATA = '''Checkout service exception\n
java.io.IOException: File uploading failed, retrying...\n
    at java.io.FileOutputStream.writeBytes(Native Method)\n
    at java.io.FileOutputStream.write(Unknown Source)\n
    at GHOST.GInputStream.readFile(GInputStream.java:79n\n
    at GHOST.GInputStream.handleIncoming(GInputStream.java:29)'''

# Metric data
METRIC_DATA_FILENAME = "metric_data.csv"
NORMAL_DATA_FILENAME = "normal_data.csv"
ABNORMAL_DATA_FILENAME = "abnormal_data.csv"
HEADER = "timestamp,system.net.bytes_sent[core server],system.cpu.idle[core server],system.mem.committed_as[core " \
         "server],system.swap.free[core server,system.disk.in_use[core server],system.load.norm.15[core server]," \
         "system.cpu.user[core server],system.io.r_await[core server],system.mem.total[core server]," \
         "system.mem.buffered[core server],system.mem.page_tables[core server],system.mem.pct_usable[core server]," \
         "system.mem.used[core server],system.net.packets_in.count[core server],system.cpu.iowait[core server]," \
         "system.io.util[core server],system.disk.total[core server],system.io.await[core server],system.io.rkb_s[" \
         "core server],system.disk.free[core server],system.cpu.system[core server],system.disk.write_time_pct[core " \
         "server],system.io.svctm[core server],system.mem.commit_limit[core server],system.io.wrqm_s[core server]," \
         "system.mem.usable[core server],system.mem.free[core server],system.swap.cached[core server],system.io.r_s[" \
         "core server],system.disk.read_time_pct[core server],system.io.w_await[core server],system.io.avg_rq_sz[core " \
         "server],system.mem.cached[core server],system.load.15[core server],system.net.packets_out.count[core " \
         "server],system.swap.used[core server],system.disk.used[core server],system.io.avg_q_sz[core server]," \
         "system.load.norm.5[core server],system.mem.shared[core server],system.load.norm.1[core server]," \
         "system.io.wkb_s[core server],system.io.rrqm_s[core server],system.load.1[core server],system.swap.total[" \
         "core server],system.load.5[core server],system.cpu.guest[core server],system.net.packets_in.error[core " \
         "server],system.mem.slab[core server],system.io.w_s[core server],system.swap.pct_free[core server]," \
         "system.cpu.stolen[core server],system.net.packets_out.error[core server],system.net.bytes_rcvd[core server] "

# Config constant
CONFIG_FILE = "config.ini"
IF_CAT = 'InsightFinder'
INSTANCE_CORE_SERVER = "core server"
DEP_INSTANCE = 'Jenkins'
# Put the ip address of the machine where the demo scripts exist, e.g. on stg the demo scripts are in the app-server node
INSTANCE_ALERT = 'Undefined Check the above comment'
# Log data constant
EVENT_ID = 'eventId'
TAG = 'tag'
DATA = 'data'
# Deployment data costant
INSTANCE_NAME = "instanceName"
TIMESTAMP = "timestamp"
MINUTE = 1000 * 60
ONE_MINUTE_SEC = 60
ONE_HOUR_SEC = ONE_MINUTE_SEC * 60
