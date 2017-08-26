#/bin/bash
ips="localhost"
ssh-keygen -t rsa -P '' -f /root/.ssh/id_rsa_IF_test
ssh-keyscan $ips >> /root/.ssh/known_hosts
for ip in $ips; do sshpass -p 102040 ssh-copy-id -i /root/.ssh/id_rsa_IF_test.pub root@$ip ;done

for ip in $ips; do ssh root@$ip "sudo useradd -m admin && sudo echo -e 'admin\\nadmin' |sudo passwd admin " ;done
for ip in $ips; do ssh root@$ip "sudo usermod -aG wheel admin " ;done
