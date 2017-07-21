# -*- encoding: utf-8 -*-

Gem::Specification.new do |gem|
  gem.name          = "fluent-plugin-out-InsightFinder"
  gem.version       = "1.0.0"
  gem.authors       = ["InsightFinder"]
  gem.email         = ["info@insightFinder.com"]
  gem.summary       = %q{A generic td-agent output plugin to send logs to our HTTP server}
  gem.description   = gem.summary
  gem.homepage      = "https://github.com/insightfinder/InsightAgent/wiki#log-streaming"
  gem.licenses      = ["Apache-2.0"]

  gem.files         = `git ls-files`.split($\)
  gem.executables   = gem.files.grep(%r{^bin/}).map{ |f| File.basename(f) }
  gem.test_files    = gem.files.grep(%r{^(test|spec|features)/})
  gem.require_paths = ["lib"]

  gem.required_ruby_version  = '>= 2.1.0'

  gem.add_runtime_dependency "yajl-ruby", "~> 1.0"
  gem.add_runtime_dependency "fluentd", [">= 0.10.0", "< 2"]
  gem.add_development_dependency "bundler"
  gem.add_development_dependency "rake"
  gem.add_development_dependency "test-unit", ">= 3.1.0"
end
