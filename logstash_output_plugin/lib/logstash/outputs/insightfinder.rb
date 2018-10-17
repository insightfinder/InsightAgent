# encoding: utf-8
require "logstash/json"
require "logstash/namespace"
require "logstash/outputs/base"
require "logstash/plugin_mixins/http_client"
require 'thread'
require "uri"
require "zlib"
require "net/https"
require "uri"
require 'net/http'

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

  # project type
  config :projectType, :validate => :string, :default => "Log"

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
    @uri = URI.parse(@url)
    @http = Net::HTTP.new(@uri.host, @uri.port)
    if @url.include? 'https'
      @http.use_ssl = true
      @http.verify_mode = OpenSSL::SSL::VERIFY_NONE
    end
    @logger.debug("Client", :client => @client.inspect)
  end # def register

  public
  def multi_receive(events)
    events.each { |event| receive(event) }
  end # def multi_receive

  public
  def receive(event)
    if event == LogStash::SHUTDOWN
      finished
      return
    end

    if @interval <= 0 # means send immediately
      send_request(content)
      return
    end

    @semaphore.synchronize {
      now = Time.now
      #Modify the event
      dd_event = Hash.new
      dd_event['eventId'] = event.timestamp.to_i * 1000
      dd_event['tag'] = event.sprintf(event.get('host'))
      dd_event['data'] = event.sprintf(event.get('message'))
      event_json = LogStash::Json.dump(dd_event)
      @pile << dd_event
      if now - @timer > @interval # ready to send
        dataBody = {"agentType" => "LogStreaming", "licenseKey" => @licenseKey, "projectName" => @projectName, "userName" => @userName, "projectType" => @projectType, "metricData" => LogStash::Json.dump(@pile)}
        send_request(dataBody)
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
    @http.finish
  end # def close

  private
  def send_request(content)
    token = @request_tokens.pop
    body = if @compress
      Zlib::Deflate.deflate(content)
    else
      content
    end

    #format data and send request
    request = Net::HTTP::Post.new(@uri.request_uri)
    begin
      request.set_form_data(content)
      response = @http.start {|http| http.request(request) }
      @logger.info("DD convo", :request => request.inspect, :response => response.inspect)
      raise unless response.code =~ /^2\d\d$/
    rescue Exception => e
      @logger.warn("Unhandled exception", :request => request.inspect, :response => response.inspect, :exception => e.inspect)
    end

  end # def send_request

  private
  def log_failure(message, opts)
    @logger.error(message, opts)
  end # def log_failure

end # class LogStash::Outputs::insightfinder
