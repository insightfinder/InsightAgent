1. build jar file
``mvn clean install -DskipTests``
2. build docker image
``sudo docker build -t kuberactions .``
3. configMap env: k8s
   ```
   k8s.insight-finder.userName
   k8s.insight-finder.license
   k8s.insight-finder.system # systemId not systemName
   k8s.insight-finder.actionServerIp #ingress url
   k8s.insight-finder.actionServerPort # optional could leave empty
   k8s.insight-finder.actionServerId # optional could leave empty
   k8s.insight-finder.actionServerName # a readable server name
   k8s.insight-finder.serverUrl # insight finder server url
5. API Doc url: /swagger-ui/index.html
