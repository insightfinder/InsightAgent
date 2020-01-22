# Offline Install
`./fetch-prereqs.sh [--remote]` can be used to get source packages for install for:
* `make` (requires `gcc` - *not* supplied as an offline package and must be installed from media or the internet)
* `python` (requires `make`)
* `pip` (requires `python`)
* `monit` (if applicable - requires `make`)
The `--remote` flag determines if the package should be downloaded whether or not a version of it is installed.
This script is fairly fragile; if it breaks, please email [support](support@insightfinder.com).

To install a tar from source, run:
```bash
./make-install.sh  # to install locally
                            # or, to install on remote machine(s):
./remote-cp-run.sh -cp <package>.tar.gz [node1 node2 nodeN [-f nodefile list_of_nodes]]
```

Also included is a script to get an offline package of `tcpdump` for installation/distribution:
```
./offline/fetch-tcpdump.sh
```

