### How to compile:

```
cd <repo dir>
mvn package
```

### How to run:

```
java -jar <appname>.jar --spring.config.location=file:<config file dir>
```

#### How to config:
## default properties
# add custom port for this tool server
server.port=
## Custom properties
# Input the clientId tenantId and clientCredentials you want to test for your teams app in the config file
clientId=d4c3b9dc-xxxx-4018-a3f0-31dc5971503c

tenantId=9edc902a-24c0-xxxx-8e0d-7fd62eb788a9   

clientCredentials=Ova8Q~yLQ8G4XQWHS4ZmMnpnt7j5OrMnxxxx~ba7  
# Set up callback in your azure app, replace localhost:9999 with your domain and port running this tool
![image](https://github.com/insightfinder/InsightAgent/assets/97707476/84476a21-fbc8-4c78-8ed7-8fcb3c592f74)

# input http://localhost:9999/test, replace localhost:9999 with your domain and port running this tool
If your setup is good for the teams integration, result will show as below:
```
Step 1: success, can get authorization from tenant: 9edc902a-24c0-475e-8e0d-7fd62eb788a9 
Step 2: success, login.microsoftonline.com is reachable 
Step 3: Success to get token, Your teams integration env is Great!
```
