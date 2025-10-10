import subprocess
import sys
import configparser

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
    config.read('config.ini')
    projects_str = config.get('InsightFinder', 'projects', fallback='')
    projects = [p.strip() for p in projects_str.split(',') if p.strip()]

    print("--- Getting Asset Hierarchy ---")
    run_script("get_asset_hierarchy.py")
    print(" --- Creating Device DB ---")
    run_script("create_device_db.py")

    for project_name in projects:
        print(f"--- Running scripts for project: {project_name} ---")
        run_script("map_insightfinder_instances.py", project_name)
        run_script("send_data_to_if.py", project_name)

    print("--- All scripts ran successfully for all projects. ---")

if __name__ == "__main__":
    main()
