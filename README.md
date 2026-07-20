# InsightAgent

InsightFinder agents can be used to monitor system performance on bare-metal machines, virtual machines, and containers.

See the individual agent folders for installation and setup instructions.
In general, agent installers assume that the following programs are installed:

* `wget`
* `python`
* `monit`
  * Not required for all agents
  * Assumes that files in `/etc/monit.d/` are included in the config

## Gitleaks setup

To help prevent secrets from being committed, developers can install Gitleaks locally and enable the repository hooks:

* Install Gitleaks. On macOS, Homebrew is a common option: `brew install gitleaks`. On Linux, users can install it using the package manager or download a release binary from the official project page at [https://github.com/gitleaks/gitleaks/releases](https://github.com/gitleaks/gitleaks/releases).
* If needed, install pre-commit. The official installation guide is available at [https://pre-commit.com/](https://pre-commit.com/). Common options include `pipx install pre-commit`, `brew install pre-commit`, or the package manager approach described there.
* Enable the hooks in this repository: `pre-commit install`
* To keep the hook definitions current, you can also run `pre-commit autoupdate` periodically.

This will run the Gitleaks checks automatically before each commit.

<!-- The wiki is very out of date and may be unnecessary -->
<!-- More details on the agents and installation details are in the wiki: https://github.com/insightfinder/InsightAgent/wiki
-->
## InsightFinder for Splunk

InsightFinder also supports a special integration with Splunk via a native Splunk app.

More details on the InsightFinder App for Splunk is available on [Splunkbase](https://splunkbase.splunk.com/app/3281/).
