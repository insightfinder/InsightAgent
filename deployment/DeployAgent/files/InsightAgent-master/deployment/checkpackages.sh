#!/bin/bash
function usage()
{
	echo "Usage: ./deployment/checkpackages.sh Use -env if you want to use use a different python virtual environment for installing dependencies"
}
if [ "$#" -eq 1 ]; then
	wget https://bootstrap.pypa.io/get-pip.py && python get-pip.py --force-reinstall --user
	sudo chown -R $USER ~/.local
    ~/.local/bin/pip install -U --force-reinstall --user virtualenv
    version=`python -c 'import sys; print(str(sys.version_info[0])+"."+str(sys.version_info[1]))'`
    python ~/.local/lib/python$version/site-packages/virtualenv.py pyenv --system-site-packages
    source pyenv/bin/activate
    pip install -r deployment/requirements
    deactivate
elif [ "$#" -eq 0 ]; then
     wget https://bootstrap.pypa.io/get-pip.py && python get-pip.py
     pip install -r deployment/requirements
else
    usage
	exit 1
fi