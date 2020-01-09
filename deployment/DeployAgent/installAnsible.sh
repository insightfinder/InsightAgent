#!/bin/bash
INSTALL=0
if [ ! $(which ansible-playbook) ]; then
    INSTALL=1
fi

if [ -f /etc/centos-release ] || [ -f /etc/redhat-release ] || [ -f /etc/oracle-release ] || [ -f /etc/system-release ] || grep -q 'Amazon Linux' /etc/system-release; then
    LIST_VERSIONS="sudo yum --showduplicates list ansible"
    if [[ ${INSTALL} -eq 1 ]]; then
        # sudo yum install -y epel-release
        sudo yum install -y ansible
    fi
elif [ -f /etc/debian_version ] || [ grep -qi ubuntu /etc/lsb-release ] || grep -qi ubuntu /etc/os-release; then
    LIST_VERSIONS="sudo apt-cache policy ansible"
    if [[ ${INSTALL} -eq 1 ]]; then
        apt-get -y update
        apt-get -y install software-properties-common
        apt-add-repository -y ppa:ansible/ansible
        apt-get -y update
        apt-get install -y ansible
    fi
else
    echo 'WARN: Could not detect distro or distro unsupported'
    exit 1
fi

if [[ ${INSTALL} -eq 1 ]]; then
    echo "Installed ansible."
else
    echo "Ansible already installed."
fi

echo "Please check that the version is <=2.7:"
echo "$(ansible --version)"
echo "Otherwise, check available versions with"
echo "${LIST_VERSIONS}"

exit 0
