### Config Variables
* `metrics`: Metrics to report to InsightFinder. Multiple `sar` flags have been grouped as below; see `man sar` for more information on each flag.
    * `os`: `-vw` (host level)
    * `mem`: `-Rr` (host level only)
    * `paging`: `-BSW` (host level only)
    * `io`: 
        * Host Level: `-bHq`
        * Device Level: `-y`
    * `network`: 
        * Device Level: `-n DEV -n EDEV`
        * Host Level: `-n NFS -n NFSD -n SOCK -n SOCK6 -n IP -n EIP -n ICMP -n EICMP -n TCP -n ETCP -n UDP -n IP6 -n EIP6 -n ICMP6 -n EICMP6 -n UDP6`
    * `filesystem`: `-dF` (device level)
    * `power`: `-m FAN -m IN -m TEMP -m USB` (device level)
    * `cpu`: `-m CPU -m FREQ -u ALL -P ALL` (per-core and host level)
* `exclude_devices`: Set to True to not report device-level data. Note that this will prevent CPU, power, filesystem, some I/O, and some network metrics from being reported. By default, device-level data is reported.
* `replay_days`: A comma-delimited list of days within the last fiscal month to replay (from `/var/log/sa/saDD`)
* `replay_sa_files`: A comma-delimited list of sa files or directories to replay.
* **`user_name`**: User name in InsightFinder
* **`license_key`**: License Key from your Account Profile in the InsightFinder UI. 
* `token`: Token from your Account Profile in the InsightFinder UI. 
* **`project_name`**: Name of the project created in the InsightFinder UI. 
* **`project_type`**: Type of the project - one of `metric, metricreplay, log, logreplay, incident, incidentreplay, alert, alertreplay, deployment, deploymentreplay`.
* **`sampling_interval`**: How frequently data is collected. Should match the interval used in cron.
* `chunk_size_kb`: Size of chunks (in KB) to send to InsightFinder. Default is `2048`.
* `if_url`: URL for InsightFinder. Default is `https://app.insightfinder.com`.
* `if_http_proxy`: HTTP proxy used to connect to InsightFinder.
* `if_https_proxy`: As above, but HTTPS.
