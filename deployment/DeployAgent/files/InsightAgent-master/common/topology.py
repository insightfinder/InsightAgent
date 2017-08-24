# -*- coding: utf-8 -*-
import pwd
import os
import re
import glob
import json
import time
from optparse import OptionParser
import netifaces

'''
this script gathers network info from the local system and outputs a json file
'''
usage = "Usage: %prog [options]"
parser = OptionParser(usage=usage)
parser.add_option("-d", "--directory",
                  action="store", dest="homepath", help="Directory to run from")
(options, args) = parser.parse_args()

if options.homepath is None:
    homepath = os.getcwd()
else:
    homepath = options.homepath
datadir = 'data/'

PROC_TCP4 = "/proc/net/tcp"
PROC_UDP4 = "/proc/net/udp"
PROC_TCP6 = "/proc/net/tcp6"
PROC_UDP6 = "/proc/net/udp6"
PROC_PACKET = "/proc/net/packet"
TCP_STATE = {
    '01': 'ESTABLISHED',
    '02': 'SYN_SENT',
    '03': 'SYN_RECV',
    '04': 'FIN_WAIT1',
    '05': 'FIN_WAIT2',
    '06': 'TIME_WAIT',
    '07': 'CLOSE',
    '08': 'CLOSE_WAIT',
    '09': 'LAST_ACK',
    '0A': 'LISTEN',
    '0B': 'CLOSING'
}


def _tcp4load():
    ''' Read the table of tcp connections & remove the header  '''
    with open(PROC_TCP4, 'r') as f:
        content = f.readlines()
        content.pop(0)
    return content


def _tcp6load():
    ''' Read the table of tcpv6 connections & remove the header'''
    with open(PROC_TCP6, 'r') as f:
        content = f.readlines()
        content.pop(0)
    return content


def _hex2dec(s):
    return str(int(s, 16))


def _ip(s):
    ip = [(_hex2dec(s[6:8])), (_hex2dec(s[4:6])),
          (_hex2dec(s[2:4])), (_hex2dec(s[0:2]))]
    return '.'.join(ip)


def _ip6(s):
    # this may need to be converted to a string to work properly.
    ip = [s[6:8], s[4:6], s[2:4], s[0:2], s[12:14], s[14:16], s[10:12], s[8:10],
          s[22:24], s[20:22], s[18:20], s[16:18], s[30:32], s[28:30], s[26:28], s[24:26]]
    return ':'.join(ip)


def _remove_empty(array):
    return [x for x in array if x != '']


def _convert_ipv4_port(array):
    host, port = array.split(':')
    return _ip(host), _hex2dec(port)


def _convert_ipv6_port(array):
    host, port = array.split(':')
    return _ip6(host), _hex2dec(port)


def netstat_tcp4():
    '''
    Function to return a list with status of tcp connections on Linux systems.
    Please note that in order to return the pid of of a network process running on the
    system, this script must be ran as root.
    '''

    tcpcontent = _tcp4load()
    tcpresult = []
    for line in tcpcontent:
        # Split lines and remove empty spaces.
        line_array = _remove_empty(line.split(' '))
        # Convert ipaddress and port from hex to decimal.
        l_host, l_port = _convert_ipv4_port(line_array[1])
        r_host, r_port = _convert_ipv4_port(line_array[2])
        tcp_id = line_array[0]
        state = TCP_STATE[line_array[3]]
        uid = pwd.getpwuid(int(line_array[7]))[0]       # Get user from UID.
        # Need the inode to get process pid.
        inode = line_array[9]
        pid = _get_pid_of_inode(inode)                  # Get pid prom inode.
        try:                                            # try read the process name.
            exe = os.readlink('/proc/' + pid + '/exe')
        except:
            exe = None

        nline = [tcp_id, uid, l_host + ':' + l_port,
                 r_host + ':' + r_port, state, pid, exe]
        tcpresult.append(nline)
    return tcpresult


def netstat_tcp6():
    '''
    This function returns a list of tcp connections utilizing ipv6. Please note that in order to return the pid of of a
    network process running on the system, this script must be ran as root.
    '''
    tcpcontent = _tcp6load()
    tcpresult = []
    for line in tcpcontent:
        line_array = _remove_empty(line.split(' '))
        l_host, l_port = _convert_ipv6_port(line_array[1])
        r_host, r_port = _convert_ipv6_port(line_array[2])
        tcp_id = line_array[0]
        state = TCP_STATE[line_array[3]]
        uid = pwd.getpwuid(int(line_array[7]))[0]
        inode = line_array[9]
        pid = _get_pid_of_inode(inode)
        try:                                            # try read the process name.
            exe = os.readlink('/proc/' + pid + '/exe')
        except:
            exe = None

        nline = [tcp_id, uid, l_host + ':' + l_port,
                 r_host + ':' + r_port, state, pid, exe]
        tcpresult.append(nline)
    return tcpresult


def _get_pid_of_inode(inode):
    '''
    To retrieve the process pid, check every running process and look for one using
    the given inode.
    '''
    for item in glob.glob('/proc/[0-9]*/fd/[0-9]*'):
        try:
            if re.search(inode, os.readlink(item)):
                return item.split('/')[2]
        except:
            pass
    return None

def get_interfaces():

    interfaces = netifaces.interfaces()
    interfaces.remove('lo')

    out_interfaces = dict()

    for interface in interfaces:
        addrs = netifaces.ifaddresses(interface)
        out_addrs = dict()
        if netifaces.AF_INET in addrs.keys():
            out_addrs["ipv4"] = addrs[netifaces.AF_INET]
        if netifaces.AF_INET6 in addrs.keys():
            out_addrs["ipv6"] = addrs[netifaces.AF_INET6]
        out_interfaces[interface] = out_addrs

    return out_interfaces


if __name__ == '__main__':

    # Output:Connection ID, UID, localhost:localport, remotehost:remoteport,
    # state, pid, exe name"
    tcpv4_result = netstat_tcp4()
    tcpv6_result = netstat_tcp6()
    # get the timestamp
    ts = int(time.time())

    # servers = machines I am getting connected to
    # clients = machines who are connecting to me
    serversv4 = []
    serversv6 = []
    clientsv4 = []
    clientsv6 = []
    listenersv4 = []
    listenersv6 = []
    listening_portsv4 = []
    listening_portsv6 = []
    interfaces = get_interfaces()

    for conn_tcp in tcpv4_result:
        if conn_tcp[4] == "LISTEN":
            listenersv4.append(conn_tcp[2])
            listening_portsv4.append(conn_tcp[2].split(":")[1])

    for conn_tcp in tcpv4_result:
        if conn_tcp[4] != "LISTEN":
            if conn_tcp[2].split(":")[1] in listening_portsv4:
                clientsv4.append(conn_tcp[3] + "-" + conn_tcp[2])
            else:
                serversv4.append(conn_tcp[2] + "-" + conn_tcp[3])

    for conn_tcp in tcpv6_result:
        if conn_tcp[4] == "LISTEN":
            listening_portsv6.append(conn_tcp[2].split(":")[16])
            listenersv6.append(conn_tcp[2])

    for conn_tcp in tcpv6_result:
        if conn_tcp[4] != "LISTEN":
            if conn_tcp[2].split(":")[16] in listening_portsv6:
                clientsv6.append(conn_tcp[3] + "-" + conn_tcp[2])
            else:
                serversv6.append(conn_tcp[2] + "-" + conn_tcp[3])

    result = {}



    result["outboundv4"] = serversv4
    result["outboundv6"] = serversv6
    result["inboundv4"] = clientsv4
    result["inboundv6"] = clientsv6
    #result["listenersv4"] = listenersv4
    #result["listenersv6"] = listenersv6
    result["timestamp"] = str(int(round(ts/60)*60))+'000'
    result["interfaces"] = interfaces
    #
    # for idx, item in enumerate(listening_portsv4):
    #     listening_portsv4[idx] = ":" + item
    #
    # for idx, item in enumerate(listening_portsv6):
    #     listening_portsv6[idx] = ":" + item
    with open(os.path.join(homepath, datadir + "topology.json"), 'w+') as outfile:
        json.dump(result, outfile)
