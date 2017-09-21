Gem::Specification.new do |s|
  s.name          = "logstash-output-insightfinder"
  s.version       = "1.0.0"
  s.licenses      = ["Apache-2.0"]
  s.summary       = "Deliever the log to insightfinder cloud service."
  s.description   = "This gem is a Logstash output plugin to deliver the log to insightfinder host."
  s.authors       = ["insightfinder"]
  s.email         = "info@insightfinder.com"
  s.require_paths = ["lib"]

  # Files
  s.files = Dir["lib/**/*","spec/**/*","vendor/**/*","*.gemspec","*.md","CONTRIBUTORS","Gemfile","LICENSE","NOTICE.TXT"]
   # Tests
  s.test_files = s.files.grep(%r{^(test|spec|features)/})

  # Special flag to let us know this is actually a logstash plugin
  s.metadata = { "logstash_plugin" => "true", "logstash_group" => "output" }

  # Gem dependencies
  s.add_runtime_dependency "logstash-core-plugin-api", "~> 2.0"
  s.add_runtime_dependency "logstash-codec-plain"
  s.add_development_dependency "logstash-devutils"
end
