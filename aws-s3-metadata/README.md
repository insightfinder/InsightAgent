# AWS S3 metadata

This agent collects metadata from AWS S3 and sends it to Insightfinder.

## Installing the Agent

### Required Dependencies:

1. Python == 3.7
1. Pip3

###### Installation Steps:

1. Download the aws-s3_metadata.tar.gz package
1. Copy the agent package to the machine that will be running the agent
1. Extract the package
1. Navigate to the extracted location
1. Configure venv and python dependencies
1. Configure agent settings
1. Test the agent
1. Add agent to the cron

The final steps are described in more detail below.

###### Configure venv and python dependencies:

Before configure python venv, please install `gcc gcc-c++` and `ca-certificates` first.

```bash
sudo yum install gcc gcc-c++ openssl-devel

sudo yum reinstall ca-certificates
```

The configure_python.sh script sets up a virtual python environment and installs all required libraries for running the
agent.

```bash
./setup/configure_python.sh
```

###### Agent configuration:

The config.ini file contains all of the configuration settings needed to connect to the AWS S3 and to stream the
metadata to InsightFinder.

The configure_python.sh script will generate a config.ini file for you; however, if you need to create a new one, you
can simply copy the config.ini.template file over the config.ini file to start over.

Populate all of the necessary fields in the config.ini file with the relevant data. More details about each field can be
found in the comments of the config.ini file and the Config Variables below.

###### Test the agent:

Once you have finished configuring the config.ini file, you can test the agent to validate the settings.

This will connect to the AWS S3, but it will not send any data to InsightFinder. This allows you to verify that
you are getting data from AWS S3 and that there are no failing exceptions in the agent configuration.

```bash
./setup/test_agent.sh
```

###### Add agent to the cron:

For the agent to run continuously, it will need to be added as a cron job.

The install_cron.sh script will add a cron file to run the agent.

```bash
# Add the cron entry, once you are ready to start streaming
sudo ./setup/install_cron.sh --monitor
```

###### Stopping the agent:

Once the cron is running, you can stop the agent removing the cron file or commenting the line in the cron file, then
kill all of it's relevant processes.

To stop the cron, you can either comment out the line in the cron file that is created, or you can delete the file
itself.

```#To comment out the line, use the # symbol at the start of the line
vi /etc/cron.d/aws-s3_metadata
# <cron>
```

```#To delete the file, run this command
sudo rm /etc/cron.d/aws-s3_metadata
```

```#To kill the agent, first print the list of processes running, then kill the agent processes based on their process ID.
ps auwx | grep getmessages_aws-s3_metadata.py
sudo kill <Processs ID>
```

### Config Variables

* `aws_access_key_id`: AWS access key
* `aws_secret_access_key`: AWS secret access key
* `aws_region`: AWS region name
* `aws_s3_bucket_name`: AWS S3 bucket name to read the files.
* `aws_s3_object_prefix`: AWS S3 object prefix to filter the files.
* `agent_http_proxy`: HTTP proxy used to connect to the agent.
* `agent_https_proxy`: As above, but HTTPS.
* **`user_name`**: User name in InsightFinder
* **`license_key`**: License Key from your Account Profile in the InsightFinder UI.
* `token`: Token from your Account Profile in the InsightFinder UI.
* **`project_name`**: Name of the project created in the InsightFinder UI, If this project is not exist, agent will
  create it automatically.
* **`run_interval`**: How frequently (in Minutes) the agent is ran. Should match the interval used in cron.
* `chunk_size_kb`: Size of chunks (in KB) to send to InsightFinder. Default is `2048`.
* `if_url`: URL for InsightFinder. Default is `https://app.insightfinder.com`.
* `if_http_proxy`: HTTP proxy used to connect to InsightFinder.
* `if_https_proxy`: As above, but HTTPS.

