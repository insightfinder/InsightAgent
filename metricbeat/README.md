These files is used to stream system metric.

1. Ansible role of metricbeat is implemented in ansible-role-metricbeat directory.

2. install-metricbeat.yml is a sample playbook used with metricbeat ansible role to install metricbeat for target machines.

   You need to set metricbeat settings according to your environment. For example, set metricbeat_outputs_conf variable with your own logstash ip and port :	
   ```
   metricbeat_outputs_conf:
   output.logstash:
   enabled: true
   hosts: ["10.10.10.11:10001"]
   ```

3. logstash-metricbeat.conf is sample logstash configuration to receive metricbeat events and convert to the format for Insightfinder API.

   You need to set project_name variable to your own metric project name :

   `mutate { add_field => { "project_name" => "metric_if_system" } }`
