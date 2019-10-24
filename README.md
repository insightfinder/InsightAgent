# InsightAgent
InsightFinder agents can be used to monitor system performance on bare-metal machines, virtual machines, and containers.

See the individual agent folders for installation and setup instructions.
In general, agent installers assume that the following programs are installed:
* `wget`
* `python`
* `monit`
    * Not required for all agents
    * Assumes that files in `/etc/monit.d/` are included in the config

<!-- The wiki is very out of date and may be unnecessary --> 
<!-- More details on the agents and installation details are in the wiki: https://github.com/insightfinder/InsightAgent/wiki
-->
# InsightFinder for Splunk
InsightFinder also supports a special integration with Splunk via a native Splunk app.

More details on the InsightFinder App for Splunk is available on [Splunkbase](https://splunkbase.splunk.com/app/3281/).
