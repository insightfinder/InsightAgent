# MySQL Log Collector
This agent collects data from MySQL and sends it to Insightfinder.

## Installing the Agent
Download the agent tarball and untar it

###### Download the agent tarball and untar it:
```bash
curl -fsSLO https://github.com/insightfinder/InsightAgent/raw/master/mysql_log_collector/mysql_log_collector.tar.gz
tar xvf mysql_log_collector.tar.gz && cd mysql_log_collector
```

###### Copy `config.ini.template` to `config.ini` and edit it:
```bash
cp config.ini.template config.ini
vi config.ini
```
Make sure to not leave any field blank.

###### Check Python version & upgrade if using Python 3
```bash
if [[ $(python -V 2>&1 | awk '{ print substr($NF, 1, 1) }') == "3" ]]; then \
2to3 -w MySqlLogCollector.py; \
else echo "No upgrade needed"; fi
```

###### Setup pip & required packages:
```bash
sudo ./pip-mysql-log.sh
```

###### Test the agent:
```bash
python MySqlLogCollector.py -t
```

###### If satisfied with the output, configure the agent to run continuously:
```bash
sudo ./cron-mysql-log.sh
```
