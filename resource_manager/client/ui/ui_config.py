import os
import json
from pathlib import Path
import logging
hostname = os.uname()[1] if hasattr(os, 'uname') else os.environ.get('COMPUTERNAME', 'localhost')
hoststr = f"{hostname}"

class UIConfig:
    """Configuration manager for the Resource Manager UI."""
    
    DEFAULT_CONFIG = {
        "theme": "light",
        "layout": "default",
        "host_table": {
            "columns": ["name", "status", "actions"],
            "pagination": True,
            "items_per_page": 10
        },
        "default_host_id": "{hoststr}",
        "ui_settings": {
            "auto_refresh": True,
            "refresh_interval": 30  # seconds
        }
    }
    
    def __init__(self, client_config=None):
        """Initialize UI configuration.
        
        Args:
            client_config: Optional ClientConfig instance
        """
        self.logger = logging.getLogger("resource_manager.ui")
        
        # Reference to client config if provided
        self.client_config = client_config
        
        # Load UI configuration
        self.config_file = self._get_config_path()
        self.settings = self._load_config()
        
    def _get_config_path(self):
        """Get the UI configuration file path."""
        if os.name == "nt":  # Windows
            base_dir = Path(os.environ.get("APPDATA", "")) / "ResourceManager"
        else:  # Unix/Linux/Mac
            base_dir = Path.home() / ".config" / "resource_manager"
            
        return str(base_dir / "ui_config.json")
    
    def _load_config(self):
        """Load UI configuration from file or create default."""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    return json.load(f)
            else:
                # Create directory if it doesn't exist
                os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
                
                # Write default config
                with open(self.config_file, 'w') as f:
                    json.dump(self.DEFAULT_CONFIG, f, indent=2)
                
                return self.DEFAULT_CONFIG.copy()
        except Exception as e:
            self.logger.warning(f"Could not load UI config, using defaults: {e}")
            return self.DEFAULT_CONFIG.copy()
    
    def save(self):
        """Save UI configuration to file."""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.settings, f, indent=2)
            return True
        except Exception as e:
            self.logger.error(f"Error saving UI config: {e}")
            return False
    
    def get_host_table_config(self):
        """Get host table configuration."""
        return self.settings.get("host_table", self.DEFAULT_CONFIG["host_table"])
    
    def get_default_host_id(self):
        """Get the default host ID."""
        # First try from UI config
        host_id = self.settings.get("default_host_id", f"{hoststr}")
        
        # Validate the host exists if we have client_config
        if self.client_config and host_id not in self.client_config.get_all_hosts():
            # Fall back to first available host or default
            hosts = self.client_config.get_all_hosts()
            host_id = hosts[0] if hosts else hoststr
            
            # Update the setting
            self.settings["default_host_id"] = host_id
            self.save()
            
        return host_id
    
    def set_default_host_id(self, host_id):
        """Set the default host ID."""
        if self.client_config and host_id not in self.client_config.get_all_hosts():
            return False
            
        self.settings["default_host_id"] = host_id
        return self.save()
