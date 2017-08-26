# InsightAgent: MetricFileReplay
Agent Type: MetricFileReplay

Platform: Linux

InsightAgent support replay mode of metric csv files in which the data from the csv file is read and sent to insightfinder server. The user can send multiple files to the same project. InsightFinder backend can automatically fuse multiple files into one csv data based on timestamps. A sample file looks like the following:
```csv
timestamp, cpu[node1]:1,memory[node1]:2,disk_read[node1]:3,disk_write[node1]:4,network_receive[node1]:5,network_send[node1]:6, cpu[node2]:1,memory[node2]:2,disk_read[node2]:3,disk_write[node2]:4,network_receive[node2]:5,network_send[node2]:6, cpu[node3]:1,memory[node3]:2,disk_read[node3]:3,disk_write[node3]:4,network_receive[node3]:5,network_send[node3]:6, cpu[node4]:1,memory[node4]:2,disk_read[node4]:3,disk_write[node4]:4,network_receive[node4]:5,network_send[node4]:6, cpu[node5]:1,memory[node5]:2,disk_read[node5]:3,disk_write[node5]:4,network_receive[node5]:5,network_send[node5]:6
1442555275000,8.7380231,1050.804224,2.732032,0.0,46.175,43.11,3.4068913,1138.601984,0.262144,0.0,5.853,4.709,3.5621096,1628.110848,1.800192,0.0,7.458,6.303,2.8296526,1264.095232,0.004096,0.0,5.119,4.932,3.8720168,1713.414144,0.004096,0.0,7.772,7.607
1442555336000,5.5654848,1072.873472,2.660352,0.0,30.342,27.591,1.7036675,1134.46912,0.032768,0.0,4.211,4.197,2.0013945,1621.93408,0.575488,0.0,4.033,3.53,1.7999406,1264.930816,0.0,0.0,5.399,4.72,1.6588607,1711.345664,0.0,0.0,3.266,3.376
1442555397000,7.0453733,1078.009856,2.482176,0.0,44.761,42.019,2.5252425,1133.842432,0.065536,0.0,6.401,5.038,2.2465352,1628.061696,2.117632,0.0,7.609,6.333,2.7270371,1241.595904,0.0,0.0,6.045,5.455,2.6808957,1714.76992,0.0,0.0,6.111,5.851
1442555457000,7.3391743,1097.367552,2.711552,0.0,37.253,35.301,3.3210812,1139.24096,0.098304,0.0,6.902,6.544,2.5287536,1627.447296,1.683456,0.0,5.328,4.66,3.1230276,1213.743104,0.090112,0.0,5.626,4.671,2.6102019,1719.7056,0.0,0.0,5.153,3.885
1442555517000,6.488525,1098.46528,3.731456,0.0,49.01,46.438,2.3300133,1142.796288,0.065536,0.0,6.015,5.283,2.4738245,1637.482496,2.019328,0.0,5.822,5.963,2.687311,1200.386048,0.0,0.0,7.274,6.256,2.1199127,1721.102336,0.0,0.0,8.319,7.255
'''

##### Instructions to register a project in Insightfinder.com
- Go to the link https://insightfinder.com/
- Sign in with the user credentials or sign up for a new account.
- Go to Settings and Register for a project under "Insight Agent" tab.
- Give a project name, select Project Type as "Metric File".
- Note down the project name and license key which will be used for agent installation. The license key is also available in "User Account Information". To go to "User Account Information", click the userid on the top right corner.

##### Pre-requisites:
Python 2.7.

For Debian and Ubuntu, the following command will ensure that the required dependencies are installed:
```
sudo apt-get upgrade
sudo apt-get install build-essential libssl-dev libffi-dev python-dev wget
```
For Fedora and RHEL-derivatives, the following command will ensure that the required dependencies are installed:
```
sudo yum update
sudo yum install gcc libffi-devel python-devel openssl-devel wget
```

# Steps to use replay mode:
1) Use the following command to download the insightfinder agent code.
```
wget --no-check-certificate https://github.com/insightfinder/InsightAgent/archive/master.tar.gz -O insightagent.tar.gz
```
Untar using this command.
```
tar -xvf insightagent.tar.gz
```

2) In InsightAgent-master directory, run the following commands to install and use python virtual environment for insightfinder agent:
```
./deployment/checkpackages.sh -env
```
```
source pyenv/bin/activate
```
```
./deployment/install.sh -i PROJECT_NAME -u INSIGHTFINDER_USER_NAME -k LICENSE_KEY -s 1 -t metricFileReplay
```
3) Put data files in InsightAgent-master/data/
Make sure each file is .csv formatted, starts with a row of headers and the headers should have "timestamp" field in it.

4) Run the following command for each data file.
```
pyenv/bin/python common/reportMetrics.py -m metricFileReplay -f PATH_TO_CSVFILENAME
```
Where PATH_TO_CSVFILENAME is the path and filename of the csv file.

After using the agent, use command "deactivate" to get out of python virtual environment.

