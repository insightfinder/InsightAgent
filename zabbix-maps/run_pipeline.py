#!/usr/bin/env python3
"""
Master pipeline script to orchestrate the complete workflow:
1. Fetch map links from Zabbix and save to device_links.json
2. Update component mappings from Zabbix metadata to instance_component.json
3. Transform device links to component-based links in component_links.json
"""

import sys
import logging
import subprocess
import os

LOG_LEVEL = logging.INFO

def setup_logging():
    """Setup basic logging"""
    logging.basicConfig(
        level=LOG_LEVEL,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger(__name__)

def run_script(logger, script_name, description):
    """
    Run a Python script and check for success
    
    Args:
        logger: Logger instance
        script_name: Name of the Python script to run
        description: Human-readable description of the step
    
    Returns:
        True if successful, False otherwise
    """
    logger.info(f"\n{'='*60}")
    logger.info(f"Step: {description}")
    logger.info(f"Running: {script_name}")
    logger.info(f"{'='*60}\n")
    
    try:
        # Run the script and capture output
        result = subprocess.run(
            [sys.executable, script_name],
            capture_output=True,
            text=True,
            check=False
        )
        
        # Print stdout
        if result.stdout:
            print(result.stdout)
        
        # Print stderr if there are errors
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        
        # Check return code
        if result.returncode != 0:
            logger.error(f"Script {script_name} failed with return code {result.returncode}")
            return False
        
        logger.info(f"✓ {description} completed successfully\n")
        return True
        
    except Exception as e:
        logger.error(f"Error running {script_name}: {e}")
        return False

def check_file_exists(logger, filename, description):
    """Check if a required file exists"""
    if os.path.exists(filename):
        logger.info(f"✓ {description} found: {filename}")
        return True
    else:
        logger.error(f"✗ {description} not found: {filename}")
        return False

def main():
    """Main pipeline orchestration"""
    logger = setup_logging()
    
    logger.info("="*60)
    logger.info("Zabbix Map to Component Links Pipeline")
    logger.info("="*60)
    
    # Step 1: Fetch map links from Zabbix
    if not run_script(logger, "main.py", "Fetch map links from Zabbix"):
        logger.error("Pipeline failed at Step 1: Fetching map links")
        sys.exit(1)
    
    # Verify device_links.json was created
    if not check_file_exists(logger, "device_links.json", "Device links file"):
        logger.error("device_links.json was not created by main.py")
        sys.exit(1)
    
    # Step 2: Update component mappings from Zabbix metadata
    if not run_script(logger, "update_zabbix_components_with_tag.py", "Update component mappings"):
        logger.error("Pipeline failed at Step 2: Updating component mappings")
        sys.exit(1)
    
    # Verify instance_component.json was created
    if not check_file_exists(logger, "instance_component.json", "Component mapping file"):
        logger.error("instance_component.json was not created by update_zabbix_components_with_tag.py")
        sys.exit(1)
    
    # Step 3: Transform device links to component-based links
    if not run_script(logger, "create_component_links.py", "Create component-based links"):
        logger.error("Pipeline failed at Step 3: Creating component links")
        sys.exit(1)
    
    # Verify component_links.json was created
    if not check_file_exists(logger, "component_links.json", "Component links file"):
        logger.error("component_links.json was not created by create_component_links.py")
        sys.exit(1)
    
    # Pipeline complete
    logger.info("\n" + "="*60)
    logger.info("Pipeline completed successfully!")
    logger.info("="*60)
    logger.info("\nGenerated files:")
    logger.info("  1. device_links.json - Device-based links from Zabbix map")
    logger.info("  2. instance_component.json - Device to component name mapping")
    logger.info("  3. component_links.json - Component-based links")
    logger.info("  4. zabbix_metadata.json - Full Zabbix metadata")
    logger.info("\n")

if __name__ == "__main__":
    main()
