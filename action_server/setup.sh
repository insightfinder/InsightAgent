echo this is for ubuntu 22.04, may need changes for other OS
sudo apt update
sudo apt install python3
sudo apt install pip
sudo apt install openssl
pip3 install -r requirements.txt
chmod +x ./start.sh
echo please add command below to your crontab
echo ......start......
echo @reboot root sh $(dirname "$0")/start.sh
echo ......end......
sh $(dirname "$0")/start.sh