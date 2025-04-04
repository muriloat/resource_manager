import os
import json
import sys
from pathlib import Path
from .logging_setup import setup_client_logging

hostname = os.uname()[1] if hasattr(os, 'uname') else os.environ.get('COMPUTERNAME', 'localhost')
hoststr = f"{hostname}"

class ClientConfig:
    """Configuration manager for Resource Manager Client."""
    
    DEFAULT_CONFIG = {
        hoststr: {
            "base_url": "http://127.0.0.1:5000", 
            "timeout": 80,
            "verify_ssl": True,
            "name": "Local Server"  # Added name for UI display
        },
        "_client_settings": {
            "log_level": "ERROR",  # Default log level
            "log_file": None  
        }
    }
    
    def __init__(self, config_file=None):
        """Initialize configuration from file or defaults."""
        self.config_file = config_file or self._get_default_config_path()
        self.hosts = {}
        self._load_config()
        
        # Ensure default host exists
        if hoststr not in self.hosts:
            self.hosts[hoststr] = self.DEFAULT_CONFIG[hoststr]  # Changed to use hoststr directly
            self.save()
    
        # Set up logging
        client_settings = self.hosts.get("_client_settings", self.DEFAULT_CONFIG["_client_settings"])
        self.logger = setup_client_logging(
            log_file=client_settings.get("log_file"),
            log_level=client_settings.get("log_level")
        )
        
        self.logger.debug(f"Initialized client configuration from {self.config_file}")


    def _get_default_config_path(self):
        """Get the default configuration file path."""
        config_dir = os.environ.get("RESOURCE_MANAGER_CONFIG_DIR")
        
        if config_dir:
            path = Path(config_dir) / "client_config.json"
        else:
            # Default to user config directory or home directory
            if os.name == "nt":  # Windows
                path = Path(os.environ["APPDATA"]) / "ResourceManager" / "client_config.json"
            else:  # Unix/Linux/Mac
                path = Path.home() / ".config" / "resource_manager" / "client_config.json"
        
        return str(path)
    
    def _load_config(self):
        """Load configuration from file or create default."""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    self.hosts = json.load(f)
            else:
                # Create directory if it doesn't exist
                os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
                
                # Write default config
                self.hosts = self.DEFAULT_CONFIG
                self.save()
        except Exception as e:
            print(f"Warning: Could not load config, using defaults: {e}")
            self.hosts = self.DEFAULT_CONFIG
    
    def save(self):
        """Save configuration to file."""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.hosts, f, indent=2)
            return True
        except Exception as e:
            print(f"Error saving config: {e}")
            return False
    
    def get_host_config(self, host_id=hoststr):
        """Get configuration for a specific host."""
        return self.hosts.get(host_id, self.DEFAULT_CONFIG[hoststr])  # Changed to use hoststr directly
    
    def set_host_config(self, host_id, config):
        """Set or update configuration for a host."""
        self.hosts[host_id] = config
        return self.save()
    
    def get_all_hosts(self):
        """Get IDs of all configured hosts."""
        # Filter out special configuration entries
        return [host_id for host_id in self.hosts.keys() if not host_id.startswith('_')]
    
    def remove_host(self, host_id):
        """Remove a host from configuration."""
        if host_id in self.hosts and host_id != hoststr:
            del self.hosts[host_id]
            return self.save()
        return False
    
    def set_log_level(self, level):
        """Set the logging level."""
        if level.upper() in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
            client_settings = self.hosts.get("_client_settings", {})
            client_settings["log_level"] = level.upper()
            self.hosts["_client_settings"] = client_settings
            
            # Update the logger
            import logging
            self.logger.setLevel(getattr(logging, level.upper()))
            
            self.save()
            return True
        return False