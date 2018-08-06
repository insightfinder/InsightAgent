# insightfinder-statsd-backend

A plugin to send statsD data to Insightfinder

## Installation

    $ cd /path/to/statsd-dir
    $ npm install insightfinder-statsd-backend
    
## Configuration

```js
insightFinderLicenseKey: "your_license_key" // You can get it from this page: https://app.insightfinder.com/account-info
insightFinderProjectName: "project_to_send_data_to"
insightFinderUserName: "your_insightfinder_username" // You can get it from this page: https://app.insightfinder.com/account-info
insightFinderApiHost: "hostname_to_send_data_to" // Its https://app.insightfinder.com by default
```

## How to enable
Add insightfinder-statsd-backend to your list of statsd backends:

```js
backends: ["insightfinder-statsd-backend"]
