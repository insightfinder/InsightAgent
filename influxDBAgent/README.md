1. use maven to package:
```
mvn clean package
```

2. Use jdk19 to run agent: 
```
$JAVA_HOME/bin/java -jar target/influxDBAgent-1.0-SNAPSHOT-jar-with-dependencies.jar /home/elay/config.properties
```

3. POC Discussion
SQL query? Authentication (HTTPS)?