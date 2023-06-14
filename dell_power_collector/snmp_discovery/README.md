# Snmp Discovery

## Configuration
The config file is snmp_discovery.ini. The following are the parameters that can be configured:

``ip-range``: The IP net range to scan, use CIDR notation. For set multiple range, use whitespace to seperate them. For example, `192.168.31.204/32 192.168.1.1/24`
``community``: The community string to use for SNMPv1 and SNMPv2c requests. 
``port``: The port to use for SNMP requests. Default is 161.
``mib``: The MIB file to use for SNMP requests. Default is ``
