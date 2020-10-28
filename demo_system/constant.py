IF = "IF"
LICENSE_KEY = "license_key"
USER_NAME = "user_name"
SERVER_URL = "server_url"
START_TIME = "start_time"
NORMAL_TIME = "normal_time"
ABNORMAL_TIME = "abnormal_time"
PROJECT_NAME = "project_name"
DATA_TYPE = "data_type"
REVERSE_DEPLOYMENT = "reverse_deployment"
LOG = "Log"
DEPLOYMENT = "Deployment"
WEB = "Web"
METRIC = "Metric"
LOG_PROJECT_NAME = "demo_log"
DEPLOYMENT_PROJECT_NAME = "demo_deployment"
WEB_PROJECT_NAME = "demo_web"
METRIC_PROJECT_NAME = "demo_metric"
DATA_TYPE_NORMAL = "normal"
DATA_TYPE_ABNORMAL = "abnormal"
DATE_TIME_FORMAT_MINUTE = "%Y-%m-%dT%H:%M:00"
DATE_TIME_FORMAT = "%Y-%m-%dT%H:%M:%S"

# Deployment data
DEPLOYMENT_DATA = '''jobType: DEPLOY\n
buildStatus: SUCCESS\n
gitLog: commit fee8238318dfe94d849604a8da7dff0bd59234d9\n
Merge: 2302b64a2 ef394aa82\n
Author: Tom <Tom@insightfinder.com>\n
    Merge pull request #5010 from DEMO/II-7100_checkout_service_feature\n
    Adding a new checkout service feature '''

DEPLOYMENT_DATA_REVERSE = '''jobType: DEPLOY\n
buildStatus: SUCCESS\n
gitLog: commit adr148898791juhssiue93710249ad19j9101ije0\n
Merge: 21412r1sa r4teaw1qw\n
Author: Tom <Tom@insightfinder.com>\n
    Merge pull request #5011 from DEMO/HOTFIX_reverse_checkout_service_feature\n
    Reverse release from Tom Anderson '''

# Web data
WEB_INCIDENT_DATA = "Production 911: Checkout server returns 500 error"
WEB_NORMAL_DATA = ["User checked the dash board page", "User changed the profile setting", "User logged out",
                   "User logged in"]

# Log data
NORMAL_LOG_DATA = ["Start writing to file.", "File writing finished"]
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
LOG_INSTANCE = "core server"
DEP_INSTANCE = 'Jenkins'
# Put the ip address of the machine where the demo scripts exist, e.g. on stg the demo scripts are in the app-server node
# WEB_INSTANCE = 'ip-172-31-52-141.ec2.internal'
WEB_INSTANCE = ''
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
