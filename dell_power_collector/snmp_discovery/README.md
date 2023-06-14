## Installation

The snmp_discovery tool uses [nmap](https://nmap.org/) to scan the snmp ports of a given IP range and then uses snmpwalk to get the system 
information of the devices that have snmp enabled. The nmap is provided as standalone binary, we need to install it
manually. 

### Install nmap on Linux

```bash
sudo apt-get update
sudo apt-get install nmap
```

