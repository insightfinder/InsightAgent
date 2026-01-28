#!/usr/bin/env python3
"""
Main orchestrator script to run:
1. get_venues.py
2. fetch_zabbix_device_tags.py
3. send_device_relations_to_IF.py
in order.
"""
import subprocess
import sys

def run_script(script_name):
    print(f"\n=== Running {script_name} ===")
    result = subprocess.run([sys.executable, script_name])
    if result.returncode != 0:
        print(f"Error: {script_name} failed with exit code {result.returncode}")
        sys.exit(result.returncode)
    print(f"=== Finished {script_name} ===\n")

def main():
    run_script('get_venues.py')
    run_script('fetch_zabbix_device_tags.py')
    run_script('send_device_relations_to_IF.py')
    print("\nAll steps completed successfully!")

if __name__ == "__main__":
    main()
