# InsightAgent: jolokia-cassandra-stream
Platform: Linux, Python 2.7

This agent is used with jolokia to stream cassandra metric to InsightFinder.

Installation:

* Download latest Jolokia JVM agent jar file (e.g jolokia-jvm-1.6.2-agent.jar )from "https://jolokia.org/download.html"
* Copy the downloaded jar file to Cassandra’s lib folder (e.g. /usr/share/cassandra/lib)

* In cassandra-env.sh file, set javaagent to JVM_OPTS, for example add this line:

  JVM_OPTS="$JVM_OPTS -javaagent:$CASSANDRA_HOME/lib/jolokia-jvm-1.6.2-agent.jar=port=7777,host=10.10.10.31"

  In this line, 7777 is the agent port, or default 8778 if not specify it. 10.10.10.31 is the cassandra node's hostname or ip.

* Restart Cassandra service.

* To check if jolokia works, access "http://10.10.10.31:7777/jolokia/read/java.lang:type=Memory/HeapMemoryUsage" in web browser, you should see such response:

  ```
  {"request":{"mbean":"java.lang:type=Memory","attribute":"HeapMemoryUsage","type":"read"},"value":{"init":1073741824,"committed":894828544,"max":894828544,"used":301860792},"timestamp":1603091049,"status":200}
  ```

* Download this jolokia-cassandra-stream folder, create config.ini from config.ini.template and fill it.

* Create a csv file "instancelist.csv" in which each line contains a hostname/ip and its jolokia agent address, it's corresponding to above JVM_OPTS setting , for example:

  10.10.10.31,http://10.10.10.31:7777

* Add cron job to run getmetrics_jolokia.py every minute, for example:

  `* * * * * root /usr/bin/python /root/jolokia-cassandra-stream/getmetrics_jolokia.py -d /root/jolokia-cassandra-stream &>/dev/null`

  It sends cassandra metric to Insightfinder every miniute.