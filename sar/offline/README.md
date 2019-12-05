# Offline Install
These scripts provide support for installing sysstat from source. To use them, simply run (from an internet-connected machine):
```bash
./prepare-git-repo.sh
```
`fetch-prereqs.sh [--remote]` can be used to get source packages for install for:
* `make` (requires `gcc` - *not* supplied as an offline package and must be installed from media or the internet)
* `python` (requires `make`)
* `pip` (requires `python`)
* `monit` (if applicable - requires `make`)
The `--remote` flag determines if the package should be downloaded whether or not a version of it is installed.
This script is fairly fragile; if it breaks, please email [support](support@insightfinder.com).

To install a tar from source, run:
```bash
./make-install.sh   # to install locally
                    # or, to install on remote machine(s):
./remote-cp-run.sh -cp <package>.tar.gz [node1 node2 nodeN [-f nodefile list_of_nodes]]
```

If the installation does not automatically create a cron entry, something like the following should be ran on the target machine as root.
```bash
echo -e "*/1 * * * * root $(find /usr/local /usr -type f -name sa1 -print -quit 2>/dev/null) -S XALL 1 1\n" | sudo tee /etc/cron.d/sysstat
```
This sets up `sysstat` to collect all (`-s XALL`) data every 1 minute.

To distribute cron on target machine(s):
```bash
nodes="node1 node2"
nodes=$(cat nodefile)
for node in ${nodes};
do
    ssh ${node} "sudo echo -e '*/1 * * * * root \$(find /usr/local /usr -type f -name sa1 -print -quit 2>/dev/null) -S XALL 1 1\n' | sudo tee /etc/cron.d/sysstat"
done
```

