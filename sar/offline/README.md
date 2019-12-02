# Offline Install

These scripts provide support for installing sysstat from source. To use them, simply run (from an internet-connected machine):
```bash
./prepare-git-repo.sh
```

```bash
./make-install.sh   # to install locally
                    # or, to install on remote machine(s):
./remote-cp-run.sh -t sysstat-make.tar.gz -s make-install.sh -p sysstat [-f nodefile list_of_nodes]
```

If the installation does not automatically create a cron entry, something like the following should be ran on the target machine as root.
```bash
echo -e "*/1 * * * * root $(find /usr/local/lib64 /usr/lib64 -type f -name sa1 -print 2>/dev/null) -S XALL 1 1\n" > /etc/cron.d/sysstat
```
This sets up `sysstat` to collect all (`-s XALL`) data every 1 minute.

To distribute cron on target machine(s):
```bash
nodes="node1 node2"
nodes=$(cat nodefile)
for node in ${nodes};
do
    ssh ${node} "sudo echo -e '*/1 * * * * root \$(find /usr/local/lib64 /usr/lib64 -type f -name sa1 -print 2>/dev/null) -S XALL 1 1\n' | sudo tee /etc/cron.d/sysstat"
done
```

