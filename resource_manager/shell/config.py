from ..client.config import ClientConfig

class ShellConfig:
    """Configuration for the Shell Manager tool."""
    
    # Tool-specific default settings
    DEFAULT_TOOL_CONFIG = {
        "refresh_interval": 10,
        "log_lines": 25,
        "log_time_range": "30 minutes ago",
        "log_file": "shell_manager.log",
        "log_level": "ERROR",
        "active_host": "default",
        # Confirmation settings
        "stop_confirm": True,
        "restart_confirm": True,
        "reload_confirm": True,
        "enable_confirm": True,
        "disable_confirm": True
    }
    
    def __init__(self, config_file=None):
        """Initialize configuration from ClientConfig and tool-specific settings."""
        # Load client configuration
        self.client_config = ClientConfig(config_file)
        
        # Tool-specific settings
        self.tool_settings = self.DEFAULT_TOOL_CONFIG.copy()
        
        # Load tool settings from the same file (different section)
        self._load_tool_settings()
    
    def _load_tool_settings(self):
        """Load tool-specific settings from client config file."""
        tool_settings = self.client_config.hosts.get("_tool_settings", {})
        if tool_settings:
            self.tool_settings.update(tool_settings)
    
    def save_tool_settings(self):
        """Save tool settings to config file."""
        self.client_config.hosts["_tool_settings"] = self.tool_settings
        return self.client_config.save()
    
    def get_current_host_id(self):
        """Get the currently active host ID."""
        return self.tool_settings.get("active_host", "default")
    
    def set_current_host_id(self, host_id):
        """Set the active host ID."""
        if host_id in self.client_config.get_all_hosts():
            self.tool_settings["active_host"] = host_id
            return self.save_tool_settings()
        return False
    
    def get_client_config(self, host_id=None):
        """Get client configuration for the specified or active host."""
        if host_id is None:
            host_id = self.get_current_host_id()
        return self.client_config.get_host_config(host_id)
    
    def get_all_hosts(self):
        """Get all available host configurations."""
        hosts = {}
        for host_id in self.client_config.get_all_hosts():
            # Skip internal tool settings
            if not host_id.startswith("_"):
                hosts[host_id] = self.client_config.get_host_config(host_id)
        return hosts
    
    def get_tool_settings(self):
        """Get all tool-specific settings."""
        return self.tool_settings.copy()
    
    def update_tool_settings(self, settings):
        """Update tool settings."""
        self.tool_settings.update(settings)
        return self.save_tool_settings()
    
    def get_setting(self, key, default=None):
        """Get a specific tool setting."""
        return self.tool_settings.get(key, default)
    
    def set_setting(self, key, value):
        """Set a specific tool setting."""
        self.tool_settings[key] = value
        return self.save_tool_settings()
    
    def ensure_default_host(self):
        """Ensure at least the default host exists in configuration."""
        if "default" not in self.client_config.hosts:
            self.client_config.hosts["default"] = {
                "base_url": "http://192.168.10.95:5000",
                "timeout": 10,
                "verify_ssl": True
            }
            self.client_config.save()
            return True
        return False