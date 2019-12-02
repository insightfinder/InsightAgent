{{{
# Template
This is a template `README.d` for use when there is a __git__ repo that can be installed using `./configure && make && make install`.

{{TARGET}} will be replaced in the same way the `target` file is used in these scripts.
{{EXTRA}} will be replaced with `.EXTRA.md`
}}}
# Offline Install
These scripts provide support for installing {{TARGET}} from source. To use them, simply run (from an internet-connected machine):
```bash
./prepare-git-repo.sh
```

```bash
./make-install.sh   # to install locally
                    # or, to install on remote machine(s):
./remote-cp-run.sh -t {{TARGET}}-make.tar.gz -s make-install.sh -p {{TARGET}} [-f nodefile list_of_nodes]
```
{{EXTRA}}
