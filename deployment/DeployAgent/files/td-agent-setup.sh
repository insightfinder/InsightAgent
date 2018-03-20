#!/bin/bash

groupadd -r fluent
useradd -r -c "Fluent user" -g fluent -s /bin/bash -d /var/lib/fluent fluent
mkdir -p /etc/fluent/ /var/run/fluent/ /var/log/fluent/ /var/lib/fluent/ /etc/fluent/plugin
chown -R fluent:fluent /etc/fluent/ /var/run/fluent/ /var/log/fluent/ /var/lib/fluent/
# sudo -u /usr/lib64/ruby/gems/2.1.0/bin/fluent fluentd --setup /etc/fluent/
sudo -u fluent fluentd --setup /etc/fluent/
sudo touch /var/run/fluent/fluent.pid
