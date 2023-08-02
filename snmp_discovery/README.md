# Snmp Discovery

## scan command

The scan command is used to scan the snmp devices on the network and add then to the agent. Use the following command to
run the scan command:

```
./snmp_discovery scan
```

The config file is snmp_discovery.ini. The following are the parameters that can be configured:

``ip-range``: The IP net range to scan, use CIDR notation. For set multiple range, use whitespace to seperate them. For
example, `192.168.31.204/32 192.168.1.1/24`
``community``: The community string to use for SNMPv1 and SNMPv2c requests.
``port``: The port to use for SNMP requests. Default is 161.
``mib``: The MIB file to use for SNMP requests. Default is ``

## trap command

The trap command starts a snmp trap server to receive the traps from the devices. Use the following command to run the
trap command:

```
./snmp_discovery trap
```

The command options are:

``address``: The IP address and port to listen on. Default is ``0.0.0.0:162``

### trap config
To send trap to the trap server, add the following config in the `/etc/snmp/snmpt.conf` and then restart the snmpd

```
# /etc/snmp/snmpt.conf
trapsink 0.0.0.0 public
```