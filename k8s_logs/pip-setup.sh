#!/bin/bash
# hard-coded definition. TODO: add any required pip packages
PIP_PACKAGES="urllib3 certifi chardet idna requests docutils statistics six python-dateutil pytz configparser pyasn1 pyasn1-modules cachetools rsa oauthlib requests-oauthlib google-auth pyyaml setuptools websocket-client ipaddress kubernetes"
if [[ -z "${PIP_PACKAGES}" ]]; then
    # try to read from stdin
    PIP_PACKAGES=$@
fi
PIP_VERSION="pip-19.2.2.tar.gz"

# run as root
if [[ $EUID -ne 0 ]]; then
   echo "This script should be ran as root. Exiting..."
   exit 1
fi

# if pip packages are needed
if [[ -n "${PIP_PACKAGES}" ]]; then
    # make sure pip is installed
    # attempt offline install
    if [[ -z $(command -v pip) ]] && [[ -x "get-pip.py" ]]; then
        echo "Package \"pip\" not installed. Attempting to install offline now..."
        $(command -v python) get-pip.py
    fi

    # attempt online install
    if [[ -z $(command -v pip) ]]; then
        echo "Package \"pip\" not installed. Attempting to install online now..."
        $(command -v python) <(curl --connect-timeout 3 https://bootstrap.pypa.io/get-pip.py)
    fi

    # if still not found, quit
    if [[ -z $(command -v pip) ]]; then
        echo "Could not install package \"pip\". Please contact support@insightfinder.com"
        exit 1
    fi

    ####
    # similar to the above, but look for pip_packages.tar.gz
    if [[ ! $(pip install --no-index --find-links='pip_packages' ${PIP_PACKAGES}) ]]; then
        if [[ ! -d "pip_packages" ]]; then
            find ../ -type f -name "pip_packages.tar.gz" -exec tar xf {} \;
        fi
        if [[ ! -d "pip_packages" ]]; then
            find / -type f -name "pip_packages.tar.gz" -exec tar xf {} \;
        fi
        if [[ ! -d "pip_packages" ]]; then
            echo "Could not find pip_packages folder or tar. Exiting..."
            exit 1
        fi
        if [[ ! $(pip install --no-index --find-links='pip_packages' ${PIP_PACKAGES}) ]]; then
            echo "Could not install all required pip_packages. Exiting..."
            exit 1
        fi
    fi
fi

