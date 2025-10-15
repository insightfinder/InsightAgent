import subprocess
import sys
import configparser
import requests
from map_insightfinder_instances import login, process_project

def run_script(script_name, *args):
    """Runs a python script and checks for errors."""
    try:
        command = [sys.executable, script_name] + list(args)
        result = subprocess.run(command, check=True, text=True)
        print(f"Successfully ran {script_name}")
    except subprocess.CalledProcessError as e:
        print(f"Error running {script_name}:")
        sys.exit(1)

def main():
    """Main function to run all scripts."""
    config = configparser.ConfigParser()
    config.read('conf.d/config.ini')
    projects_str = config.get('InsightFinder', 'projects', fallback='')
    projects = [p.strip() for p in projects_str.split(',') if p.strip()]

    print("--- Getting Asset Hierarchy ---")
    run_script("get_asset_hierarchy.py")
    print(" --- Creating Device DB ---")
    run_script("create_device_db.py")

    # Login once to InsightFinder for all projects
    print("--- Logging into InsightFinder (shared session for all projects) ---")
    session = requests.Session()
    csrf_token = login(session)
    print("Successfully logged in to InsightFinder.")

    try:
        for project_name in projects:
            print(f"\n--- Running scripts for project: {project_name} ---")
            # Call process_project directly with shared session and token
            process_project(project_name, session=session, csrf_token=csrf_token)
            run_script("send_data_to_if.py", project_name)
    finally:
        # Clean up session
        session.close()

    print("\n--- All scripts ran successfully for all projects. ---")

if __name__ == "__main__":
    main()
