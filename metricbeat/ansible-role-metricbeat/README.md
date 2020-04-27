Ansible Role: metricbeat
=========

Install metricbeat offline to collect system metric for CentOS/RedHat 7.

Requirements
------------

None.

Role Variables
--------------

Below are available variables with default value:

* metricbeat_version: 7.6.2

  The version of metricbeat to install. (Mandatory)	

* metricbeat_conf_file: /etc/metricbeat/metricbeat.yml

  The path of metricbeat configuration file. (Mandatory)

* metricbeat_modules_system_period: 60s

  How often the metricsets are executed. (Mandatory)

* metricbeat_inputs_conf:

  Inputs section of metricbeat configuration, must be dict variable. (Optional)

* metricbeat_general_conf:

  General section of metricbeat configuration, must be dict variable. (Optional)

* metricbeat_outputs_conf:

  Outputs section of metricbeat configuration, must be dict variable. (Optional)

  If it's empty, file output will be used by default and the output file is under /tmp/metricbeat/. 

Dependencies
------------

None.

Example Playbook
----------------

```
---
- hosts: all
  become: yes
  tasks:
    - import_role:
        name: metricbeat
      vars:
        metricbeat_general_conf:
          tags: ["if"]
        metricbeat_outputs_conf:
          output.logstash:
            enabled: true
            hosts: ["10.10.10.11:10001"]

```
