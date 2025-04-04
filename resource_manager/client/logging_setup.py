import os
import sys
import logging
from pathlib import Path

def setup_client_logging(log_file=None, log_level=None):
    """Set up logging for the client module.
    
    Args:
        log_file: Path to log file. If None, logs to a default location.
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
                  If None, defaults to ERROR.
    
    Returns:
        Logger instance for the client module.
    """
    # Determine log level
    if log_level is None:
        log_level = os.environ.get("RESOURCE_MANAGER_LOG_LEVEL", "ERROR")
    
    # Convert string level to logging constant
    try:
        level = getattr(logging, log_level.upper(), logging.ERROR)
    except (AttributeError, TypeError):
        level = logging.ERROR
    
    # Determine log file path
    if log_file is None:
        log_file = os.environ.get("RESOURCE_MANAGER_LOG_FILE")
        
    if log_file:
        # If it's a relative path, resolve it against project root
        if not os.path.isabs(log_file):
            project_root = Path(__file__).absolute().parents[2]
            log_file = str(project_root / log_file)
    else:
        # Use project-relative location instead of user home
        # Get the project root (3 levels up from this file)
        project_root = Path(__file__).absolute().parents[2]
        log_dir = project_root / "logs"
        
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = str(log_dir / "client.log")
        except (PermissionError, FileNotFoundError):
            # If we can't create the directory, use a temp directory
            import tempfile
            log_dir = Path(tempfile.gettempdir()) / "resource_manager" / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = str(log_dir / "client.log")
    
    # Configure the root logger if not already configured
    root_logger = logging.getLogger()
    if not root_logger.handlers:
        logging.basicConfig(
            level=logging.WARNING,  # Default level for other loggers
            format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    
    # Create client logger
    logger = logging.getLogger("resource_manager")
    logger.setLevel(level)
    
    # Remove existing handlers to avoid duplicates on reconfiguration
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # Add file handler
    try:
        # Ensure the directory exists
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(level)
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
            '%Y-%m-%d %H:%M:%S'
        ))
        logger.addHandler(file_handler)
    except (PermissionError, FileNotFoundError) as e:
        # Fallback to stderr if file can't be opened
        print(f"Warning: Could not open log file {log_file}: {e}", file=sys.stderr)
        print(f"Logging to stderr instead", file=sys.stderr)
        
        stderr_handler = logging.StreamHandler()
        stderr_handler.setLevel(level)
        stderr_handler.setFormatter(logging.Formatter(
            '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
            '%Y-%m-%d %H:%M:%S'
        ))
        logger.addHandler(stderr_handler)
    
    return logger