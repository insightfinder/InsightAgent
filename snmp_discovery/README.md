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
To send trap to the trap server, add the following config in the `/etc/snmp/snmpd.conf` and then restart the snmpd

```
# /etc/snmp/snmpd.conf
trapsink 0.0.0.0 public
rocommunity public
```

To send a sample SNMP trap information.

**-v** 2c specifies SNMP version 2c.

**-c** public specifies the SNMP community string (you can replace this with your configured community string).

**localhost** is the target host.

**1.3.6.1.2.1.1.6.0** is the OID for the sysLocation MIB.

**"This is a test trap"** is the value to be sent in the trap.
```
snmptrap -v 2c -c public localhost '' 1.3.6.1.2.1.1.6.0 s int 4
```
