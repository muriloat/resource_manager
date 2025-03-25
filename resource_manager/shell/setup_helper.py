import os
import json
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

def create_default_config():
    """Create default configuration file if it doesn't exist.
    
    Returns:
        str: Path to the configuration file
    """
    # Determine config path
    config_dir = os.environ.get("RESOURCE_MANAGER_CONFIG_DIR")
    
    if config_dir:
        config_path = Path(config_dir) / "client_config.json"
    else:
        if os.name == "nt":  # Windows
            config_path = Path(os.environ.get("APPDATA", "")) / "ResourceManager" / "client_config.json"
        else:  # Unix/Linux/Mac
            config_path = Path.home() / ".config" / "resource_manager" / "client_config.json"
    
    # Create directory if it doesn't exist
    config_path.parent.mkdir(parents=True, exist_ok=True)
    
    # If config file doesn't exist, create it with default values
    if not config_path.exists():
        default_config = {
            "default": {
                "base_url": "http://localhost:5000",
                "timeout": 10,
                "verify_ssl": True,
                "name": "Default Host"
            },
            "_client_settings": {
                "log_level": "DEBUG",
                "log_file": "client.log"
            },
            "_tool_settings": {
                "refresh_interval": 10,
                "log_lines": 25,
                "log_time_range": "30 minutes ago",
                "log_file": "shell_manager.log",
                "log_level": "DEBUG",
                "active_host": "default",
                "stop_confirm": True,
                "restart_confirm": True,
                "reload_confirm": True,
                "enable_confirm": False,
                "disable_confirm": False
            }
        }
        
        with open(config_path, 'w') as f:
            json.dump(default_config, f, indent=2)
        
        print(f"Created default configuration at: {config_path}")
    
    return str(config_path)
