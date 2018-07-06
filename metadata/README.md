## Upload meta-data for a Insightfinder project
Agent Type: Meta-data upload
Platform: Linux

This scripts allows sending meta-data(topology) csv files to Insightfinder.

```csv
test_case_id,ip1,ip2
59885e66f861b22536ac4264,10.9.88.2,10.9.88.43
59885e8ef861b22538ac4264,10.9.88.2,10.9.88.43
```

##### Instructions to register a project in Insightfinder.com
- Go to the link https://insightfinder.com/
- Sign in with the user credentials or sign up for a new account.
- Go to Settings and Register for a project under "Insight Agent" tab.
- Give a project name, select Project Type as "Metric File".
- Note down the project name and license key which will be used for agent installation. The license key is also available in "User Account Information". To go to "User Account Information", click the userid on the top right corner.

### Prerequisites:
The machine should alreday have an agent sending data to a project for which you want to upload the metadata.

### Sending Data

Run the following command for each data file.
```
sudo python /root/InsightAgent-master/metadata/get_metadata.py -p topology -f PATH_TO_CSVFILENAME
```
Where PATH_TO_CSVFILENAME is the path and filename of the meta-data csv file.
