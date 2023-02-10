# Collectd Agent Deployment

This directory contains the necessary files to deploy the collectd-agent. The inventory file, `hosts`, contains the variables required to configure the agent. The `install.yml` file will deploy the agent to the target machines listed in the inventory file. The `roles` directory contains the Ansible yaml files necessary to get the agent up and running.

## Usage

To deploy the collectd-agent, edit the `hosts` file and supply the required parameters for the agent along with the hosts/nodes you plan to install this agent on. The parameters required are:

- `report_url`
- `project_name`
- `user_name`
- `license_key`
- `sampling_interval`
- `data_disks`

Once the parameters have been supplied, the agent can be deployed with the command:

```
ansible-playbook install.yml -i hosts
```

This will deploy the agent to all hosts listed in the inventory file. To further customize the collectd service based on what metrics to collect, the `collectd.conf.js` file may be modified. Additionally, the python agent is run with a cron job configured in the ansible role file. While the agent is running the python agent output is stored in a `reporting.out` and errors are reported to `reporting.err` respectively.