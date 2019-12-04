# Offline Install

These scripts provide support for installing  from source. To use them, simply run (from an internet-connected machine):
```bash
./prepare-git-repo.sh
```

```bash
./make-install.sh   # to install locally
                    # or, to install on remote machine(s):
./remote-cp-run.sh -t -make.tar.gz -s make-install.sh -p  [-f nodefile list_of_nodes]
```
