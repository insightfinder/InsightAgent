#!/bin/bash
if [ ! $(which ansible-playbook) ]; then
  if [ -f /etc/centos-release ] || [ -f /etc/redhat-release ] || [ -f /etc/oracle-release ] || [ -f /etc/system-release ] || grep -q 'Amazon Linux' /etc/system-release; then
    # sudo yum install -y epel-release
    sudo yum install -y ansible
    LIST_VERSIONS="sudo yum --showduplicates list ansible"
  elif [ -f /etc/debian_version ] || [ grep -qi ubuntu /etc/lsb-release ] || grep -qi ubuntu /etc/os-release; then
    apt-get -y update
    apt-get -y install software-properties-common
    apt-add-repository -y ppa:ansible/ansible
    apt-get -y update
    apt-get install -y ansible
    LIST_VERSIONS="sudo apt-cache policy ansible"
  else
    echo 'WARN: Could not detect distro or distro unsupported'
    echo 'WARN: Trying to install ansible via pip without some dependencies'
    echo 'WARN: Not all functionality of ansible may be available'
    exit 1
  fi

fi

echo "Installed ansible. Please check that the version is <=2.7:"
echo "$(ansible --version)"
echo "Otherwise, check available versions with\n${LIST_VERSIONS}"

exit 0
