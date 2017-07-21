# InsightAgent
InsightFinder performance metric agents can be used to monitor system performance on bare-metal machines, virtual machines and for docker containers.

The following types of agents are available:

 - AWS EC2
 - cadvisor
 - cgroup
 - collectd
 - daemonset
 - DataDog
 - Docker Remote API
 - Elastic Search
 - Log File Replay
 - Hypervisor (i.e., VMware)
 - Jolokia
 - KVM
 - Metric File Replay

More details on the agents and installation details are in the wiki: https://github.com/insightfinder/InsightAgent/wiki

# Log File Agent
InsightFinder supports fluentd/td-agent which is available as a package install for most platforms.  We provide an output plugin that allows you to simply configure a new "match" configuration for your agent (sample configuration provided) and your data will be sent to InsightFinder.  More details are available in the wiki.

# InsightFinder for Splunk
InsightFinder also supports a special integration with Splunk via a native Splunk app.

More details on the InsightFinder for Splunk app is available at https://splunkbase.splunk.com/app/3281/

