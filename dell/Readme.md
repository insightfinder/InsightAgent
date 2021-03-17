# Anomaly Alert Agent

## Platform: Python3

## Install: 
pip install -r requirements.txt

## Run
### once: 
python anomaly_alert.py


### cron 

for example, run once every 5 minutes , do this

```
sudo crontab -e
*/5 * * * *  <path_to_script>/run.sh  >> ~/cron.log 2>&1
```

