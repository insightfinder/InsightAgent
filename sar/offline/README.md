# Offline Install
These scripts provide support for installing sar from source. To use them, simply run

```bash
./prepare-git-repo.sh
./make-install.sh   # to install locally
                    # or, to install on remote machine(s):
./remote-cp-run.sh -t sysstat-make.tar.gz -s make-install.sh -p sysstat [-f nodefile list_of_nodes]
```

See [sysstat/sysstat](https://github.com/sysstat/sysstat) for more.
