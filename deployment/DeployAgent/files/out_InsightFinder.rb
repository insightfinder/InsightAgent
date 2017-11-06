# encoding: utf-8
#require 'fluent/output'
module Fluent
  # Main Output plugin class
  class HttpBufferedOutput < Fluent::BufferedOutput
    Fluent::Plugin.register_output('InsightFinder', self)

    def initialize
      super
      require 'net/http'
      require 'uri'
      require 'json'
      require 'socket'
    end
    $maxtimestamp = 0
    $mintimestamp = 0
    # Endpoint URL ex. localhost.local/api/
    config_param :destinationHost, :string

    # statuses under which to retry
    config_param :http_retry_statuses, :string, default: ''

    # read timeout for the http call
    config_param :http_read_timeout, :float, default: 2.0

    # open timeout for the http call
    config_param :http_open_timeout, :float, default: 2.0

    config_param :userName, :string

    config_param :projectName, :string

    config_param :licenseKey, :string

    config_param :instanceType, :string

    config_param :instanceName, :string

    def configure(conf)
      super

      # Check if endpoint URL is valid
      unless @destinationHost =~ /^#{URI.regexp}$/
        fail Fluent::ConfigError, 'destinationHost invalid'
      end

      begin
        @uri = URI.parse(@destinationHost)
      rescue URI::InvalidURIError
        raise Fluent::ConfigError, 'destinationHost invalid'
      end

      # Parse http statuses
      @statuses = @http_retry_statuses.split(',').map { |status| status.to_i }

      @statuses = [] if @statuses.nil?

      @http = Net::HTTP.new(@uri.host, @uri.port)
      if @destinationHost.include? 'https'
        @http.use_ssl = true
      end
      @http.read_timeout = @http_read_timeout
      @http.open_timeout = @http_open_timeout
    end

    def start
      super
    end

    def shutdown
      super
      begin
        @http.finish
      rescue
      end
    end

    def format(tag, time, record)
      [tag, time, record].to_msgpack
    end

    def write(chunk)
      data = []
      chunk.msgpack_each do |(tag, time, record)|
      	#time_hash = {:timestamp => time, :data => temp_hash_for_record["data"]}
      	time_hash = {"tag" => tag.to_s, "timestamp" => (time*1000).to_s, "data" => record["data"]}
        data << time_hash
        if $maxtimestamp == 0
          $maxtimestamp = time
        else
          if $maxtimestamp < time 
            $maxtimestamp = time 
          end
        end
        if $mintimestamp == 0
          $mintimestamp = time
        else
          if $mintimestamp > time
            $mintimestamp = time
          end
        end

        #time_hash = {"data" => record["data"]}
        #data << JSON.generate(time_hash)
        #data << JSON.generate(time_hash)       
         #data << JSON.parse(record)
      end
      #respond_with myhash.to_json
      request = create_request(data)

      begin
        response = @http.start do |http|
          request = create_request(data)
          http.request request
        end
        $log.warn "Response: #{response.body} Code: response.code.to_i"
        if @statuses.include? response.code.to_i
          # Raise an exception so that fluent retries
          fail "Server returned bad status: #{response.code}"
        end
      rescue IOError, EOFError, SystemCallError => e
        # server didn't respond
        $log.warn "Net::HTTP.#{request.method.capitalize} raises exception: #{e.class}, '#{e.message}'"
      ensure
        begin
          @http.finish
        rescue
        end
      end
    end

    protected

      def create_request(data)
        request = Net::HTTP::Post.new(@uri.request_uri)
        # Headers
        request['Content-Type'] = 'application/json'
        #request['userName']  =  @userName
        #request['projectName'] = @projectName
        #request['licenseKey'] =  @licenseKey
        #request['destinationHost'] = @destinationHost
        #request['userName'] = 'Chen'
        #request['projectName'] = 'RealMadrid'
        #request['licenseKey'] = '123123123'
        # Body
        #request.body = JSON.dump(data)
        data = JSON.generate(data)
        #Iname = @instanceName
        #if @instanceName.to_s.empty? 
           #Iname = Socket.gethostname
        #Iname = "werty"
        if @instanceName.to_s.empty?
            hash_test = {"userName" => @userName, "projectName" => @projectName, "licenseKey" => @licenseKey, "metricData" => data, "minTimestamp" => ($mintimestamp*1000).to_s, "maxTimestamp" => ($maxtimestamp*1000 + 999).to_s, "agentType" => "td-agentPlugin", "instanceType" => @instanceType, "instanceName" => Socket.gethostname}
        else
            hash_test = {"userName" => @userName, "projectName" => @projectName, "licenseKey" => @licenseKey, "metricData" => data, "minTimestamp" => ($mintimestamp*1000).to_s, "maxTimestamp" => ($maxtimestamp*1000 + 999).to_s, "agentType" => "td-agentPlugin", "instanceType" => @instanceType, "instanceName" => @instanceName}
        end    
        #request.body = '1234567890987654321'
        request.set_form_data(hash_test)
         #request.set_form_data(JSON)
         #request.body = JSON.dump(data)
        request
      end
  end
end
