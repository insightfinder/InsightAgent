#!/usr/bin/env python3
"""
Script to transform device-based links to component-based links
Reads device_links.json and instance_component.json and creates component_links.json
"""

import json
import sys
import logging

# Output configuration
DEVICE_LINKS_FILE = 'device_links.json'
COMPONENT_MAPPING_FILE = 'instance_component.json'
OUTPUT_FILE = 'component_links.json'
LOG_LEVEL = logging.INFO

def setup_logging():
    """Setup basic logging"""
    logging.basicConfig(
        level=LOG_LEVEL,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger(__name__)

def load_json_file(logger, filename):
    """Load JSON data from file"""
    try:
        with open(filename, 'r') as f:
            data = json.load(f)
        logger.info(f"Loaded data from {filename}")
        return data
    except FileNotFoundError:
        logger.error(f"File not found: {filename}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in {filename}: {e}")
        return None
    except Exception as e:
        logger.error(f"Error loading {filename}: {e}")
        return None

def create_component_links(logger, device_links, component_mapping):
    """
    Transform device links to component links
    
    Args:
        device_links: List of dicts with 's' (source) and 't' (target) device names
        component_mapping: Dict mapping device names to component names
    
    Returns:
        List of component-based links with statistics
    """
    component_links = []
    component_link_set = set()  # To avoid duplicates
    
    skipped_links = []
    mapped_count = 0
    
    for link in device_links:
        source_device = link.get('s')
        target_device = link.get('t')
        
        # Look up component names
        source_component = component_mapping.get(source_device)
        target_component = component_mapping.get(target_device)
        
        # Check if both devices have component mappings
        if source_component and target_component:
            # Create component link (avoid duplicates)
            link_tuple = (source_component, target_component)
            
            if link_tuple not in component_link_set:
                component_link_set.add(link_tuple)
                component_links.append({
                    "s": source_component,
                    "t": target_component
                })
                mapped_count += 1
        else:
            # Track skipped links
            skipped_links.append({
                "source_device": source_device,
                "target_device": target_device,
                "source_component": source_component,
                "target_component": target_component,
                "reason": "Missing component mapping"
            })
    
    # Log statistics
    logger.info(f"Component links transformation complete:")
    logger.info(f"  Total device links: {len(device_links)}")
    logger.info(f"  Mapped to component links: {mapped_count}")
    logger.info(f"  Unique component links: {len(component_links)}")
    logger.info(f"  Skipped links (no mapping): {len(skipped_links)}")
    
    if skipped_links:
        logger.warning(f"Skipped {len(skipped_links)} links due to missing component mappings:")
        for skipped in skipped_links[:5]:  # Show first 5
            logger.warning(f"  {skipped['source_device']} -> {skipped['target_device']}")
        if len(skipped_links) > 5:
            logger.warning(f"  ... and {len(skipped_links) - 5} more")
    
    return component_links, skipped_links

def save_component_links(logger, component_links, skipped_links, output_file):
    """Save component links and metadata to JSON file"""
    try:
        output_data = {
            "component_links": component_links,
            "statistics": {
                "total_links": len(component_links),
                "skipped_links": len(skipped_links)
            },
            "skipped_links": skipped_links
        }
        
        with open(output_file, 'w') as f:
            json.dump(output_data, f, indent=2)
        
        logger.info(f"Saved {len(component_links)} component links to {output_file}")
        return True
    except Exception as e:
        logger.error(f"Failed to save component links: {e}")
        return False

def main():
    """Main function"""
    logger = setup_logging()
    
    # Load device links
    logger.info(f"Loading device links from {DEVICE_LINKS_FILE}...")
    device_links = load_json_file(logger, DEVICE_LINKS_FILE)
    if device_links is None:
        logger.error("Failed to load device links. Please run main.py first.")
        sys.exit(1)
    
    # Load component mapping
    logger.info(f"Loading component mapping from {COMPONENT_MAPPING_FILE}...")
    component_mapping = load_json_file(logger, COMPONENT_MAPPING_FILE)
    if component_mapping is None:
        logger.error("Failed to load component mapping. Please run update_zabbix_components_with_tag.py first.")
        sys.exit(1)
    
    # Transform device links to component links
    logger.info("Transforming device links to component links...")
    component_links, skipped_links = create_component_links(logger, device_links, component_mapping)
    
    if not component_links:
        logger.warning("No component links were created. Check your mappings.")
        sys.exit(1)
    
    # Save component links
    if not save_component_links(logger, component_links, skipped_links, OUTPUT_FILE):
        sys.exit(1)
    
    logger.info("Component links creation complete!")
    
    # Display component type summary
    component_types = {}
    for link in component_links:
        source = link['s']
        target = link['t']
        
        # Count source components
        component_types[source] = component_types.get(source, 0) + 1
        
        # Count target components
        component_types[target] = component_types.get(target, 0) + 1
    
    logger.info("\nComponent types involved in links:")
    for comp_type, count in sorted(component_types.items(), key=lambda x: x[1], reverse=True):
        logger.info(f"  {comp_type}: {count} connections")

if __name__ == "__main__":
    main()
