{{{
# Template
This is a template `README.d` for use when there is a __git__ repo that can be installed using `./configure && make && make install`.

{{TARGET}} will be replaced in the same way the `target` file is used in these scripts.
{{EXTRA}} will be replaced with `.EXTRA.md`
}}}
# Offline Install
{{{TARGET
These scripts provide support for installing {{TARGET}} from source. To use them, simply run (from an internet-connected machine):
```bash
./prepare-git-repo.sh
```

TARGET}}}
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
{{EXTRA}}
