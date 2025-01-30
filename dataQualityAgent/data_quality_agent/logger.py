import logging

LOG_FORMAT = "%(asctime)s [%(levelname)s] (%(name)s): %(message)s"
def setLoggingLevel(level):
    logging.basicConfig(level=level, format=LOG_FORMAT)

def get_logger(name):
    """
    Returns a logger with the specified name.
    This logger can be imported and used across multiple modules.
    """
    logger = logging.getLogger(name) 
    return logger
