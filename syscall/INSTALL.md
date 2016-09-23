# Install-LTTng-in-AWS

System Environment
--------

- `LTTNG version`: LTTng 2.8 "Isseki Nicho"
- `AMI version`: Amazon Linux AMI release 2016.03
- `AMI kernel version`: 4.1.10-17.31.amzn1.x86_64


Prerequisite
--------

```
    sudo yum install popt-devel.x86_64
    sudo yum install libxml2-devel.x86_64
    sudo yum install libuuid-devel.x86_64
```   
- `For installing urcu`: (https://github.com/urcu/userspace-rcu)
```
    sudo yum install libtool.x86_64 
```
- `check what kernel package installed`:
```
    rpm -qa | grep kernel-
```
- `install kernel source tree`: (For installing LTTng-modules. Install kernel headers/full kernel source tree)
```
    yum install kernel-devel.x86_64 
```
after it, there will be dir /usr/src/kernels/4.4.10-22.54.amzn1.x86_64
- `For installing babeltrace`: (https://github.com/efficios/babeltrace)
You will find what package is missing when you ```./configure``` the babeltrace.
```
    yum install glib2.x86_64 glib2-devel.x86_64
    yum install bison.x86_64 bison-devel.x86_64
    yum install flex.x86_64 flex_devel.x86_64
    yum install elfutils-libelf.x86_64 elfutils-libelf-devel.x86_64
    yum install libdwarf.x86_64 libdwarf-devel.x86_64
```
(sometime, it still says: configure: error: Missing libdw (from elfutils >= 0.154) which is required by debug info. You can disable this feature using --disable-debug-info.), re-install elfutils:
``` yum install elfutils.x86_64 elfutils-devel.x86_64``` 
    

Building
--------

- To build LTTng-UST, do: (https://github.com/lttng/lttng-ust)
```
    ./configure
    make
    sudo make install
    sudo ldconfig
```

- To build LTTng-tools, do: (https://github.com/lttng/lttng-tools)
```
    ./configure
    make
    sudo make install
    sudo ldconfig
``` 

- To build LTTng-modules, do: (https://github.com/lttng/lttng-modules)
```
    make
    sudo make modules_install
    sudo depmod -a
```

Hints
---
```
    error: virtual memory exhausted: Cannot allocate memory 
```
The problem is that the working files for the compiler are in /tmp... causing a double hit on memory.
(http://www.linuxquestions.org/questions/linux-newbie-8/solved-virtual-memory-exhausted-cannot-allocate-memory-4175507767/)
- `swap` made it workable: http://www.cyberciti.biz/faq/linux-add-a-swap-file-howto/
