#!/bin/bash
wget https://bootstrap.pypa.io/get-pip.py && python get-pip.py --force-reinstall --user
sudo chown -R $USER /home/$USER/.local
/home/$USER/.local/bin/pip install -U --force-reinstall --user virtualenv
version=`python -c 'import sys; print(str(sys.version_info[0])+"."+str(sys.version_info[1]))'`
python  /home/$USER/.local/lib/python$version/site-packages/virtualenv.py pyenv
source pyenv/bin/activate
pip install -r deployment/requirementsHost
deactivate
