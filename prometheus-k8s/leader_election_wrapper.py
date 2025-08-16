#!/usr/bin/env python3
"""
Leader Election Wrapper for Prometheus Agent

This wrapper implements Kubernetes leader election to ensure only one replica
of the prometheus agent collects data, preventing duplicates when scaling.

The wrapper runs the original getmessages_prometheus.py script only when
this pod is elected as the leader.
"""

import logging
import os
import signal
import subprocess
import sys
import time
import datetime
import threading
from kubernetes import client, config
from kubernetes.client.rest import ApiException

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("leader-election-wrapper")


class LeaderElectionWrapper:
    def __init__(self):
        self.namespace = os.getenv("NAMESPACE", "default")
        self.pod_name = os.getenv("HOSTNAME", "prometheus-agent-unknown")
        self.lease_name = os.getenv("LEASE_NAME", "prometheus-agent-leader")
        self.lease_duration = int(os.getenv("LEASE_DURATION", "15"))  # seconds
        self.renew_deadline = int(os.getenv("RENEW_DEADLINE", "10"))  # seconds
        self.retry_period = int(os.getenv("RETRY_PERIOD", "2"))  # seconds

        self.is_leader = False
        self.should_stop = False
        self.subprocess = None
        self.lease_lock = threading.Lock()
        self.agent_thread = None

        # Initialize Kubernetes client
        try:
            # Try to load in-cluster config first
            config.load_incluster_config()
            logger.info("Loaded in-cluster Kubernetes configuration")
        except config.ConfigException:
            try:
                # Fallback to local kubeconfig
                config.load_kube_config()
                logger.info("Loaded local Kubernetes configuration")
            except config.ConfigException as e:
                logger.error(f"Failed to load Kubernetes configuration: {e}")
                sys.exit(1)

        self.coordination_client = client.CoordinationV1Api()

        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully"""
        logger.info(f"Received signal {signum}, shutting down...")
        self.should_stop = True
        self._stop_subprocess()

    def _stop_subprocess(self):
        """Stop the running subprocess and join agent thread if it exists"""
        if self.subprocess and self.subprocess.poll() is None:
            logger.info("Stopping prometheus agent subprocess...")
            self.subprocess.terminate()
            try:
                self.subprocess.wait(timeout=10)
                logger.info("Subprocess terminated gracefully")
            except subprocess.TimeoutExpired:
                logger.warning("Subprocess didn't terminate gracefully, killing...")
                self.subprocess.kill()
                self.subprocess.wait()
        # Join agent thread if running
        if self.agent_thread and self.agent_thread.is_alive():
            logger.info("Waiting for agent thread to exit...")
            self.agent_thread.join(timeout=10)
            self.agent_thread = None

    def _create_or_update_lease(self):
        """Create or update the leader election lease"""
        lease_name = self.lease_name
        namespace = self.namespace

        # Current time in UTC (RFC3339 format)
        now = datetime.datetime.now(datetime.UTC).isoformat("T").replace("+00:00", "Z")

        lease_spec = client.V1LeaseSpec(
            holder_identity=self.pod_name,
            lease_duration_seconds=self.lease_duration,
            acquire_time=now,
            renew_time=now,
            lease_transitions=1,
        )

        lease = client.V1Lease(
            metadata=client.V1ObjectMeta(name=lease_name, namespace=namespace),
            spec=lease_spec,
        )

        try:
            # Try to get existing lease
            existing_lease = self.coordination_client.read_namespaced_lease(
                name=lease_name, namespace=namespace
            )

            # Check if we can acquire/renew the lease
            holder = existing_lease.spec.holder_identity
            lease_time = (
                existing_lease.spec.renew_time.timestamp()
                if existing_lease.spec.renew_time
                else 0
            )
            current_time = time.time()

            if holder == self.pod_name:
                # We are the current leader, renew the lease
                lease.spec.acquire_time = existing_lease.spec.acquire_time
                lease.spec.lease_transitions = existing_lease.spec.lease_transitions
                lease.spec.renew_time = now

                self.coordination_client.patch_namespaced_lease(
                    name=lease_name, namespace=namespace, body=lease
                )
                return True
            elif current_time - lease_time > self.lease_duration:
                # Lease has expired, we can acquire it
                lease.spec.lease_transitions = existing_lease.spec.lease_transitions + 1

                self.coordination_client.patch_namespaced_lease(
                    name=lease_name, namespace=namespace, body=lease
                )
                logger.info(f"Acquired leadership from expired lease held by {holder}")
                return True
            else:
                # Another pod holds a valid lease
                return False

        except ApiException as e:
            if e.status == 404:
                # Lease doesn't exist, create it
                try:
                    self.coordination_client.create_namespaced_lease(
                        namespace=namespace, body=lease
                    )
                    logger.info("Created new lease and acquired leadership")
                    return True
                except ApiException as create_e:
                    logger.error(f"Failed to create lease: {create_e}")
                    return False
            else:
                logger.error(f"Failed to read lease: {e}")
                return False

    def _run_prometheus_agent(self):
        """Run the original prometheus agent script (cron.py)"""
        script_path = os.path.join(os.path.dirname(__file__), "cron.py")
        cmd = [sys.executable, script_path] + sys.argv[
            1:
        ]  # Pass through any command line arguments

        logger.info(f"Starting prometheus agent: {' '.join(cmd)}")

        try:
            self.subprocess = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1,
            )

            # Stream output from subprocess
            while True:
                try:
                    line = self.subprocess.stdout.readline()
                except Exception as e:
                    logger.warning(f"Exception reading subprocess stdout: {e}")
                    break
                if not line:
                    break
                logger.info(f"[prometheus-agent] {line.strip()}")
                if self.should_stop:
                    break

            self.subprocess.wait()
            return_code = self.subprocess.returncode

            if return_code != 0 and not self.should_stop:
                logger.error(f"Prometheus agent exited with code {return_code}")
            else:
                logger.info("Prometheus agent completed successfully")

        except Exception as e:
            logger.error(f"Failed to run prometheus agent: {e}")
        finally:
            self.subprocess = None

    def run(self):
        """Main execution loop"""
        logger.info(f"Starting leader election wrapper for pod {self.pod_name}")
        logger.info(f"Lease: {self.lease_name} in namespace {self.namespace}")
        logger.info(
            f"Lease duration: {self.lease_duration}s, renew deadline: {self.renew_deadline}s"
        )

        while not self.should_stop:
            try:
                with self.lease_lock:
                    acquired_leadership = self._create_or_update_lease()

                if acquired_leadership and not self.is_leader:
                    # We just became the leader
                    logger.info("🎉 Acquired leadership! Starting prometheus agent...")
                    self.is_leader = True

                    # Start the prometheus agent in a separate thread
                    self.agent_thread = threading.Thread(
                        target=self._run_prometheus_agent
                    )
                    self.agent_thread.daemon = True
                    self.agent_thread.start()

                elif not acquired_leadership and self.is_leader:
                    # We lost leadership
                    logger.info("❌ Lost leadership! Stopping prometheus agent...")
                    self.is_leader = False
                    self._stop_subprocess()

                elif not acquired_leadership and not self.is_leader:
                    # We are not the leader
                    logger.debug("⏳ Not the leader, waiting...")

                elif acquired_leadership and self.is_leader:
                    # We are still the leader
                    logger.debug("✅ Renewed leadership lease")

                    # Check if subprocess is still running
                    if self.subprocess and self.subprocess.poll() is not None:
                        logger.info(
                            "Prometheus agent process ended, will restart on next cycle"
                        )
                        self.subprocess = None

                        # Only restart if we're still the leader and not shutting down
                        if self.is_leader and not self.should_stop:
                            self.agent_thread = threading.Thread(
                                target=self._run_prometheus_agent
                            )
                            self.agent_thread.daemon = True
                            self.agent_thread.start()

            except Exception as e:
                logger.error(f"Error in leader election loop: {e}")
                time.sleep(self.retry_period)
                continue

            # Wait before next iteration
            time.sleep(self.retry_period)

        # Cleanup
        self._stop_subprocess()
        logger.info("Leader election wrapper stopped")


if __name__ == "__main__":
    wrapper = LeaderElectionWrapper()
    wrapper.run()
