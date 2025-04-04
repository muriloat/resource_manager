import logging
from ..resource_manager_client import ResourceManagerClient
from ..config import ClientConfig
import os
hostname = os.uname()[1] if hasattr(os, 'uname') else os.environ.get('COMPUTERNAME', 'localhost')
hoststr = f"{hostname}"

class HostManager:
    """Manages host connections and provides a unified interface for the UI."""
    
    def __init__(self, client_config=None):
        """Initialize the host manager.
        
        Args:
            client_config: Optional ClientConfig instance
        """
        self.logger = logging.getLogger("resource_manager.ui.hosts")
        self.client_config = client_config or ClientConfig()
        
        # Cache for ResourceManagerClient instances
        self.clients = {}
        
        # Initialize default client
        self._get_client(hoststr)
        
    def _get_client(self, host_id=hoststr):
        """Get or create a client for the specified host."""
        if host_id not in self.clients:
            try:
                config = self.client_config.get_host_config(host_id)
                self.clients[host_id] = ResourceManagerClient(
                    base_url=config.get("base_url"),
                    timeout=config.get("timeout", 80),
                    log_level=self.logger.level
                )
            except Exception as e:
                self.logger.error(f"Failed to create client for {host_id}: {e}")
                return None
                
        return self.clients[host_id]
    
    def get_hosts(self):
        """Get list of all configured hosts with status."""
        hosts = []
        
        for host_id in self.client_config.get_all_hosts():
            config = self.client_config.get_host_config(host_id)
            
            # Get client for this host
            client = self._get_client(host_id)
            
            # Test connection and get health status
            health_status = "unknown"
            try:
                if client:
                    health = client.check_server_health()
                    health_status = health.get("status", "unknown")
            except Exception:
                health_status = "unreachable"
            
            hosts.append({
                "id": host_id,
                "name": config.get("name", host_id),
                "url": config.get("base_url"),
                "status": health_status,
                "timeout": config.get("timeout", 80)
            })
            
        return hosts
    
    def add_host(self, host_id, name, base_url, timeout=80):
        """Add a new host configuration."""
        if not host_id or not name or not base_url:
            return False
            
        # Check if host_id already exists
        if host_id in self.client_config.get_all_hosts():
            return False
        
        # Add new host configuration
        config = {
            "name": name,
            "base_url": base_url,
            "timeout": timeout,
            "verify_ssl": True
        }
        
        result = self.client_config.set_host_config(host_id, config)
        
        # Clear client cache for this host
        if host_id in self.clients:
            del self.clients[host_id]
            
        return result
    
    def update_host(self, host_id, name, base_url, timeout=80):
        """Update an existing host configuration."""
        if not host_id or host_id not in self.client_config.get_all_hosts():
            return False
            
        # Get existing config and update
        config = self.client_config.get_host_config(host_id)
        config.update({
            "name": name,
            "base_url": base_url,
            "timeout": timeout
        })
        
        result = self.client_config.set_host_config(host_id, config)
        
        # Clear client cache for this host
        if host_id in self.clients:
            del self.clients[host_id]
            
        return result
    
    def remove_host(self, host_id):
        """Remove a host configuration."""
        # Clear client cache
        if host_id in self.clients:
            del self.clients[host_id]
            
        return self.client_config.remove_host(host_id)
    
    def test_connection(self, host_id):
        """Test connection to a host."""
        client = self._get_client(host_id)
        if not client:
            return {
                "success": False,
                "message": "Failed to create client"
            }
            
        try:
            health = client.check_server_health()
            return {
                "success": health.get("status") == "Healthy",
                "message": f"Connection {health.get('status')}",
                "health": health
            }
        except Exception as e:
            return {
                "success": False,
                "message": str(e)
            }
