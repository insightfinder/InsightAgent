#!/usr/bin/env python3

import sys
import logging
import os
sys.path.append('/home/ashvat/Documents/Github/InsightAgent/Mimosa')

from getmessages_mimosa import (
    mimosa_login, 
    query_mimosa_metrics, 
    get_agent_config_vars,
    abs_path_from_cur
)

def test_mimosa_collection():
    """Test the updated Mimosa data collection"""
    
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)
    
    # Get config
    config_ini = abs_path_from_cur('conf.d/config.ini')
    
    try:
        agent_config_vars = get_agent_config_vars(logger, config_ini)
        
        # Extract connection details
        mimosa_uri = agent_config_vars['mimosa_uri']
        username = agent_config_vars['username']
        password = agent_config_vars['password']
        verify_certs = agent_config_vars.get('verify_certs', True)
        network_id = agent_config_vars.get('network_id', '6078')
        
        logger.info(f"Testing connection to {mimosa_uri}")
        logger.info(f"Network ID: {network_id}")
        
        # Test login
        logger.info("Testing login...")
        session = mimosa_login(mimosa_uri, username, password, verify_certs)
        logger.info("✅ Login successful!")
        
        # Test metrics collection
        logger.info("Testing metrics collection...")
        metrics_data = query_mimosa_metrics(session, mimosa_uri, network_id, [], verify_certs)
        
        logger.info(f"✅ Collected {len(metrics_data)} metrics")
        
        # Show sample of collected metrics
        logger.info("\n📊 Sample of collected metrics:")
        for i, metric in enumerate(metrics_data[:10]):  # Show first 10 metrics
            logger.info(f"  {i+1}. {metric['metric_name']}: {metric['value']} (Device: {metric['device_name']})")
        
        if len(metrics_data) > 10:
            logger.info(f"  ... and {len(metrics_data) - 10} more metrics")
        
        # Show metric breakdown by type
        metric_types = {}
        for metric in metrics_data:
            metric_name = metric['metric_name']
            if metric_name not in metric_types:
                metric_types[metric_name] = 0
            metric_types[metric_name] += 1
        
        logger.info(f"\n📈 Metric types collected:")
        for metric_type, count in sorted(metric_types.items()):
            logger.info(f"  {metric_type}: {count} devices")
        
        logger.info(f"\n✅ Test completed successfully!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Test failed: {str(e)}")
        return False

if __name__ == "__main__":
    success = test_mimosa_collection()
    sys.exit(0 if success else 1)
