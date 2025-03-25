import os
import logging
from pathlib import Path
import datetime

def setup_logging(config):
    """Set up logging for the Shell Manager.
    
    Args:
        config: Configuration object with logging settings
        
    Returns:
        Logger instance for the shell manager
    """
    tool_settings = config.get_tool_settings()
    log_level_name = tool_settings.get("log_level", "DEBUG")
    log_file = tool_settings.get("log_file")
    
    # Convert string level to logging constant
    try:
        log_level = getattr(logging, log_level_name.upper())
    except (AttributeError, TypeError):
        log_level = logging.DEBUG
    
    # Set up the logger
    logger = logging.getLogger("shell_manager")
    logger.setLevel(log_level)
    
    # Remove any existing handlers to avoid duplicates
    if logger.handlers:
        for handler in logger.handlers:
            logger.removeHandler(handler)
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        '%Y-%m-%d %H:%M:%S'
    )
    
    # Add console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # Add file handler if log file is specified
    if log_file:
        # Ensure log directory exists
        if not log_file.startswith('/'):
            # Relative path - use config directory
            log_dir = Path(os.path.dirname(config.client_config.config_file)) / "logs"
            log_dir.mkdir(exist_ok=True)
            log_file = str(log_dir / log_file)
        
        try:
            file_handler = logging.FileHandler(log_file)
            file_handler.setLevel(log_level)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
            logger.info(f"Logging to file: {log_file}")
        except (PermissionError, FileNotFoundError) as e:
            logger.error(f"Could not set up file logging to {log_file}: {e}")
    
    logger.info(f"Logging initialized at level {log_level_name}")
    return logger