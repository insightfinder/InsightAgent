#!/usr/bin/env python3
"""
Main orchestrator script to run:
1. get_application_services.py     (resolve service names -> application_services.yaml)
2. fetch_servicenow_dependencies.py (pull dependency maps -> servicenow_dependencies.yaml)
3. send_dependencies_to_IF.py       (upload relations to InsightFinder)
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
    run_script('get_application_services.py')
    run_script('fetch_servicenow_dependencies.py')
    run_script('send_dependencies_to_IF.py')
    print("\nAll steps completed successfully!")

if __name__ == "__main__":
    main()
