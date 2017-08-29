# InsightAgent: syscall
Agent Type: syscall

Platform: Linux

##### Pre-requisites:
This pre-requisite is needed on the machine which launches installLttng.py.
```
Kernel version >= 2.6.36
```
Use `uname -r` to get the current kernel version and check whether it is in `/usr/src` directory. 
If not, please install `kernel-devel`, `update` and reboot your machine.   

- For AWS(Amazon Linux AMI):
```
automake, version >= 1.10,
autoconf, version >= 2.50,
bison, bison-devel,
elfutils-libelf, elfutils-libelf-devel,
flex, flex-devel,
gcc, version >= 3.2,
glibc, glibc-devel,
glib2, glib2-devel,
git,
kernel-devel,
libdwarf, libdwarf-devel,
libtool, version >= 2.2,
libxml2-devel, version >= 2.7.6,
popt, popt-devel, version >= 1.13,
uuid-devel, libuuid-devel
```
- For Ubuntu:
```
libc6, libc6-dev, 
libglib2.0-0, libglib2.0-dev,
bison,
elfutils, libelf-dev, libdw-dev,
flex,
libpopt-dev, version >= 1.13,
liburcu, version >= 0.8.0,
libxml2-dev, version >= 2.7.6,
uuid-dev
```


##### To install agent on local machine:
```
syscall/installLttng.py -d HOME_DIR
```

##### After installation, to deploy agent on local machine:
```
./getSysTrace.sh -t TRACING_INTERVAL(min)
```
