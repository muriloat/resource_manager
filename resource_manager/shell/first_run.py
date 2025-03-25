
#!/usr/bin/env python3
"""First Run Utility for Resource Manager Shell"""

import os
import sys
import json
from pathlib import Path

def ensure_config_dir():
    """Make sure config directory exists"""
    if os.name == "nt":  # Windows
        config_dir = Path(os.environ.get("APPDATA", "")) / "ResourceManager"
    else:  # Unix/Linux/Mac
        config_dir = Path.home() / ".config" / "resource_manager"
        
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir

def create_default_config(config_path):
    """Create a default configuration file"""
    default_config = {
        "default": {
            "base_url": "http://localhost:5000",
            "timeout": 10,
            "verify_ssl": True
        },
        "_client_settings": {
            "log_level": "DEBUG",
            "log_file": None
        },
        "_tool_settings": {
            "refresh_interval": 10,
            "log_lines": 25,
            "log_time_range": "30 minutes ago",
            "log_file": "shell_manager.log",
            "log_level": "DEBUG",
            "active_host": "default"
        }
    }
    
    with open(config_path, 'w') as f:
        json.dump(default_config, f, indent=2)
    return default_config

def main():
    """Run the first-time setup"""
    print("Resource Manager Shell - First Run Setup")
    print("=======================================")
    
    config_dir = ensure_config_dir()
    config_path = config_dir / "client_config.json"
    
    if config_path.exists():
        print(f"Configuration file already exists at: {config_path}")
        overwrite = input("Do you want to reset to default configuration? (y/N): ").lower() == 'y'
        if not overwrite:
            print("Setup cancelled. Keeping existing configuration.")
            return
    
    config = create_default_config(config_path)
    print(f"Created default configuration at: {config_path}")
    
    # Ask for host information
    add_host = input("Do you want to add a resource manager server? (Y/n): ").lower() != 'n'
    if add_host:
        host_id = input("Enter a name for this server [default]: ") or "default"
        host_url = input("Enter the server URL [http://localhost:5000]: ") or "http://localhost:5000"
        timeout = input("Enter request timeout in seconds [10]: ") or "10"
        
        try:
            config[host_id] = {
                "base_url": host_url,
                "timeout": int(timeout),
                "verify_ssl": True
            }
            
            if host_id != "default":
                config["_tool_settings"]["active_host"] = host_id
                
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=2)
                
            print(f"Added host '{host_id}' with URL {host_url}")
            print("Configuration saved successfully.")
        except Exception as e:
            print(f"Error saving configuration: {e}")
    
    print("\nSetup complete! You can now start the resource manager shell.")
    print("If you encounter any issues, try running with --debug flag.")

if __name__ == "__main__":
    main()
