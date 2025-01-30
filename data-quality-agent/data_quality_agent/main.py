import argparse
from data_quality_agent.config import get_config
from data_quality_agent.mapping import source_to_target_mapping
from data_quality_agent.logger import setLoggingLevel
from data_quality_agent.logger import get_logger


DEFAULT_CONFIG_PATH = "/etc/config/config.yaml"
DEFAULT_LOG_LEVEL = "INFO"

def main():
    try:

        args = parse_args()

        setLoggingLevel(args.log_level.upper())
        logger = get_logger(__name__)

        logger.info("Loading configuration")
        config = get_config(args.config)
        logger.info("Configuration loaded succesfully")

        mappings = config['mappings']
        for mapping in mappings:
            logger.info(f"Mapping found for {mappings[mapping]['source']} and {mappings[mapping]['target']}. Applying transformations")
            source_to_target_mapping(mappings[mapping], source=mappings[mapping]['source'], target=mappings[mapping]['target'])

    except Exception as e:
        logger.error("An error occured:", e)
        e.with_traceback()

def parse_args() -> dict:
    parser = argparse.ArgumentParser(description="Load configuration for the application.")
    parser.add_argument(
        "--config",
        type=str,
        default=DEFAULT_CONFIG_PATH,
        help=f"Path to the configuration file (default: {DEFAULT_CONFIG_PATH})",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default=DEFAULT_LOG_LEVEL,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set the logging level (default: INFO)",
    )
    args = parser.parse_args()
    return args


if __name__ == "__main__":
    main()