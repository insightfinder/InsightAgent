## Getting Started

### 1. Install LogStash on your machine
Following this [instruction](https://www.elastic.co/guide/en/logstash/current/getting-started-with-logstash.html) to download and install LogStash. This plugin requires Logstash 2.3 or higher to work.

### 2. Build your plugin gem
In your local Git clone, running:
```sh
gem build logstash-output-insightfinder.gemspec
```
You will get a .gem file as `logstash-output-insightfinder-1.0.0.gem`

### 3. Install plugin into LogStash
In the Logstash home, running:
```sh
bin/logstash-plugin install <path of .gem>
```

### 4. Start Logstash and send log
In the Logstash home, running:
```sh
bin/logstash -e 'input{stdin{}}output{sumologic{url=>"<url from step 1>"}}'
```
This will send any stdin input from console to insightfinder server

### Furthermore
- Try it with different input/filter/codec plugins
- Start LogStash as a service/daemon in your production environment

## Parameters
This plugin is based on [logstash-mixin-http_client](https://github.com/logstash-plugins/logstash-mixin-http_client) thus it supports all parameters like proxy, authentication, retry, etc.

And it supports following additional prarmeters:
```
  # The URL to send logs to. This should be given when creating a HTTP Source
  # on Sumo Logic web app. See http://help.sumologic.com/Send_Data/Sources/HTTP_Source
  config :url, :validate => :string, :required => true

  # The project number user is using
  config :projectName, :validate => :string, :required => true

  # user's user name
  config :userName, :validate => :string, :required => true

  # user's licenseKey
  config :licenseKey, :validate => :string, :required => true

  # Include extra HTTP headers on request if needed
  config :extra_headers, :validate => :hash, :default => []

  # The formatter of message, by default is message with timestamp and host as prefix
  config :format, :validate => :string, :default => "%{@timestamp} %{host} %{message}"

  # Hold messages for at least (x) seconds as a pile; 0 means sending every events immediately  
  config :interval, :validate => :number, :default => 0

  # Compress the payload
  config :compress, :validate => :boolean, :default => false

```
