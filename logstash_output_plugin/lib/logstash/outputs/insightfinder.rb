# encoding: utf-8
require "logstash/json"
require "logstash/namespace"
require "logstash/outputs/base"
require "logstash/plugin_mixins/http_client"
require 'thread'
require "uri"
require "zlib"

class LogStash::Outputs::Insightfinder < LogStash::Outputs::Base
  include LogStash::PluginMixins::HttpClient

  config_name "insightfinder"

  # The URL to send logs to.
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
  # use %{@json} tag to send whole event
  config :format, :validate => :string, :default => "%{@timestamp} %{host} %{message}"

  # Hold messages for at least (x) seconds as a pile; 0 means sending every events immediately
  config :interval, :validate => :number, :default => 0

  # Compress the payload
  config :compress, :validate => :boolean, :default => false

  # This lets you choose the structure and parts of the event that are sent in @json tag.
  config :json_mapping, :validate => :hash

  public
  def register
    # initialize request pool
    @request_tokens = SizedQueue.new(@pool_max)
    @pool_max.times { |t| @request_tokens << true }
    @timer = Time.now
    @pile = Array.new
    @semaphore = Mutex.new
  end # def register

  public
  def multi_receive(events)
    events.each { |event| receive(event) }
    client.execute!
  end # def multi_receive

  public
  def receive(event)
    if event == LogStash::SHUTDOWN
      finished
      return
    end

    content = format_event(event)

    if @interval <= 0 # means send immediately
      send_request(content)
      return
    end

    @semaphore.synchronize {
      now = Time.now
      @pile << content
      if now - @timer > @interval # ready to send
        dataBody = {"agentType" => "Logstash", "licenseKey" => @licenseKey, "projectName" => @projectName, "userName" => @userName, "metricData" => @pile}
        send_request(LogStash::Json.dump(dataBody))
        @timer = now
        @pile.clear
      end
    }
  end # def receive

  public
  def close
    @semaphore.synchronize {
      send_request(@pile.join($/))
      @pile.clear
    }
    client.close
  end # def close

  private
  def send_request(content)
    token = @request_tokens.pop
    body = if @compress
      Zlib::Deflate.deflate(content)
    else
      content
    end
    headers = get_headers()

    request = client.send(:parallel).send(:post, @url, :body => body, :headers => headers)
    request.on_complete do
      @request_tokens << token
    end

    request.on_success do |response|
      if response.code < 200 || response.code > 299
        log_failure(
          "HTTP response #{response.code}",
          :body => body,
          :headers => headers
      )
      end
    end

    request.on_failure do |exception|
      log_failure(
        "Could not fetch URL",
        :body => body,
        :headers => headers,
        :message => exception.message,
        :class => exception.class.name,
        :backtrace => exception.backtrace
      )
    end

    request.call
  end # def send_request

  private
  def get_headers()
    base = { "Content-Type" => "text/plain" }
    base["Content-Encoding"] = "deflate" if @compress
    base.merge(@extra_headers)
  end # def get_headers

  private
  def format_event(event)
    if @format.to_s.strip.length == 0
      LogStash::Json.dump(map_event(event))
    else
      f = if @format.include? "%{@json}"
        @format.gsub("%{@json}", LogStash::Json.dump(map_event(event)))
      else
        @format
      end
      event.sprintf(f)
    end
  end # def format_event

  private
  def map_event(event)
    if @json_mapping
      @json_mapping.reduce({}) do |acc, kv|
        k, v = kv
        acc[k] = event.sprintf(v)
        acc
      end
    else
      event.to_hash
    end
  end # def map_event

  private
  def log_failure(message, opts)
    @logger.error(message, opts)
  end # def log_failure

end # class LogStash::Outputs::insightfinder
