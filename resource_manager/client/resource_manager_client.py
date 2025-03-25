# Description: A client to consume the Resource Manager API.
# Refer to https://github.com/muriloat/resource_manager for more information.

import requests
import logging
import re, json
import datetime

class ResourceManagerClient:
    """
    A client to consume the Resource Manager API.
    
    Parameters:
        base_url (str): The base URL for the Resource Manager API (default: "http://127.0.0.1:5000")
        timeout (int): Request timeout in seconds (default: 10)
        log_level (int): Logging level (default: logging.INFO)
    """
    def __init__(self, base_url="http://127.0.0.1:5000", timeout=180, log_level=logging.DEBUG):
        self.base_url = base_url
        self.timeout = timeout
        
        # Set up logging
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(log_level)
        
        # Add handler if none exists
        if not self.logger.handlers and not logging.root.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            
        self.logger.info(f"ResourceManagerClient initialized with base_url={self.base_url}, timeout={self.timeout}")

    def _make_request(self, method, endpoint, **kwargs):
        """Helper method to make HTTP requests with enhanced error handling."""
        url = f"{self.base_url}{endpoint}"
        timeout = kwargs.pop('timeout', self.timeout)
        
        try:
            self.logger.debug(f"Making {method} request to {url}")
            response = requests.request(method, url, timeout=timeout, **kwargs)
            
            # Handle different response status codes
            if response.status_code == 404:
                error_msg = response.json().get('description', 'Resource not found')
                self.logger.error(f"Resource not found: {error_msg}")
                raise ValueError(f"Resource not found: {error_msg}")
            
            if response.status_code == 500:
                error_msg = response.json().get('description', 'Server error')
                self.logger.error(f"Server error: {error_msg}")
                raise RuntimeError(f"Server error: {error_msg}")
            
            response.raise_for_status()
            return response.json()
        except requests.exceptions.ConnectionError:
            self.logger.critical(f"Connection failed to {url} - is the server running?")
            # Instead of just raising, return a standardized error response
            return {"error": "connection_failed", "message": "Could not connect to the server. Please check if it's running."}
        except requests.exceptions.Timeout:
            self.logger.error(f"Request timed out after {timeout}s: {url}")
            return {"error": "timeout", "message": f"Request timed out after {timeout} seconds."}
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Request error: {e}")
            return {"error": "request_error", "message": str(e)}

    def print_json(self, data, title=None):
        """Pretty print JSON data with an optional title."""
        if title:
            print(f"\n=== {title} ===")

        print(json.dumps(data, indent=2))
        print("-" * 50)

    # Core methods - direct API access
    def list_services(self):
        """
        Fetch the list of available services.
        
        Returns:
            list: List of service names available on the server
        """
        return self._make_request('GET', '/services')
    
    def get_service_status(self, service_name):
        """
        Retrieve the raw status for a specific service.
        
        Args:
            service_name (str): Name of the service to query
            
        Returns:
            dict: Raw status information for the service
        """
        return self._make_request('GET', f'/services/{service_name}/status')
    
    def get_service_resource_usage(self, service_name):
        """
        Get detailed resource usage of a service including memory and CPU.
        
        Args:
            service_name (str): Name of the service to query
            
        Returns:
            dict: Resource usage details including memory and CPU
        """
        try:
            status = self.get_service_status(service_name)
            
            # Check if the status includes detailed info with our new server API
            if "details" in status and isinstance(status["details"], dict):
                return {
                    "service": service_name,
                    "memory": status["details"].get("memory", {}),
                    "cpu": status["details"].get("cpu_usage", ""),
                    "tasks": status["details"].get("tasks", {}),
                    "pid": status["details"].get("pid", None)
                }
            else:
                # If we're using an older server version, return what we can
                self.logger.warning("Detailed resource usage not available with this server version")
                return {
                    "service": service_name,
                    "running": "running" in status.get("active", "").lower()
                }
        except Exception as e:
            self.logger.error(f"Error retrieving resource usage for {service_name}: {e}")
            raise

    def get_service_metadata(self, service):
        """Extract clean metadata from service config."""
        try:
            self.logger.debug(f"Getting metadata for service: {service}")
            config = self.get_service_config(service)
            
            # Log the raw metadata
            self.logger.debug(f"Raw metadata for {service}: {config.get('metadata', {})}")
            
            metadata_dict = {}
            
            # Process all metadata keys, both with and without the prefix
            for key, value in config.get('metadata', {}).items():
                self.logger.debug(f"Processing metadata key: {key} = {value}")
                
                # Case 1: Server has already processed X-Metadata- prefixes into clean keys
                if not key.startswith('X-'):
                    metadata_dict[key] = value
                    
                # Case 2: X-Metadata- prefixed keys (process them ourselves for robustness)
                elif key.startswith('X-Metadata-'):
                    metadata_key = key.replace('X-Metadata-', '')
                    metadata_dict[metadata_key] = value
                    
                # Case 3: Other X- prefixed keys might be relevant too
                elif key.startswith('X-'):
                    # You could decide to include these with the X- prefix or handle them differently
                    # For now, just include them as-is
                    metadata_dict[key] = value
                    
            # Log the processed metadata
            self.logger.debug(f"Processed metadata for {service}: {metadata_dict}")
                
            return metadata_dict
        except Exception as e:
            self.logger.error(f"Error getting metadata for {service}: {e}", exc_info=True)
            return {}


    def get_service_config(self, service_name):
        """
        Retrieve the configuration of a service from its unit file.
        
        Args:
            service_name (str): Name of the service to query
            
        Returns:
            dict: Parsed service configuration with properly handled metadata and environment variables
        """
        try:
            config = self._make_request('GET', f'/services/{service_name}/config')
            
            # Ensure Environment is always a list for consistency
            service_section = config.get('config', {}).get('Service', {})
            if 'Environment' in service_section and not isinstance(service_section['Environment'], list):
                service_section['Environment'] = [service_section['Environment']]
                
            return config
        except Exception as e:
            self.logger.error(f"Error retrieving configuration for {service_name}: {e}")
            raise

    # Detailed Information Methods
    def get_service_details(self, service_name):
        """
        Get comprehensive details about a service including both running and boot status.
        
        Args:
            service_name (str): Name of the service to query
            
        Returns:
            dict: Dictionary with parsed service information
        """
        status = self.get_service_status(service_name)
        active_status = status.get("active_raw", "")
        loaded_status = status.get("loaded_raw", "")
        
        # Extract boot status (enabled/disabled)
        boot_status_match = re.search(r";\s*(enabled|disabled|indirect|static)", loaded_status)
        is_enabled = False
        boot_status = "unknown"
        if boot_status_match:
            boot_status = boot_status_match.group(1).lower()
            is_enabled = boot_status in ["enabled", "indirect"]
        
        return {
            "service": service_name,
            "is_running": "running" in active_status.lower(),
            "is_enabled": is_enabled,
            "boot_status": boot_status,  # Added for more detailed information
            "active_status": active_status,
            "loaded_status": loaded_status
        }

    # Boolean status methods - most commonly used
    def is_service_running(self, service_name):
        """
        Check if a service is currently running.
        
        Args:
            service_name (str): Name of the service to check
            
        Returns:
            bool: True if the service is running, False otherwise
        """
        status = self.get_service_status(service_name)
        return status.get("running", False)
    
    def is_service_enabled(self, service_name):
        """
        Check if a service is enabled to start on boot.
        
        Args:
            service_name (str): Name of the service to check
            
        Returns:
            bool: True if the service is enabled or indirect, False otherwise
        """
        status = self.get_service_status(service_name)
        return status.get("enabled", False)
    
    def get_service_logs(self, service_name, lines=50, since="24 hours ago"):
        """
        Retrieve recent logs for a service.
        
        Args:
            service_name (str): Name of the service to query
            lines (int): Number of log lines to retrieve (default: 50)
            since (str): Time specification for log retrieval (default: "24 hours ago")
                
        Returns:
            dict: Log data including entries and metadata
        """
        try:
            # URL encode the parameters to handle spaces and special characters
            import urllib.parse
            endpoint = f"/services/{service_name}/logs?lines={lines}"
            
            if since:
                # Use quote() instead of quote_plus() to avoid + signs
                encoded_since = urllib.parse.quote(since)
                endpoint += f"&since={encoded_since}"
            
            self.logger.debug(f"Requesting logs with endpoint: {endpoint}")
            
            # Ensure we use GET method
            response = self._make_request('GET', endpoint)
            
            # Check for errors in the response
            if "error" in response:
                self.logger.warning(f"Server reported error for {service_name} logs: {response['error']}")
                if "command" in response:
                    self.logger.debug(f"Command used: {response['command']}")
            
            return response
        except Exception as e:
            self.logger.error(f"Error retrieving logs for {service_name}: {e}")
            # Return a valid response even in case of error
            return {
                "service": service_name,
                "error": str(e),
                "log_count": 0,
                "logs": []
            }
        
    def get_service_logs_last_day(self, service_name, lines=50):
        """Get logs from the past 24 hours"""
        return self.get_service_logs(service_name, lines, "24 hours ago")
        
    def get_service_logs_since_boot(self, service_name, lines=100):
        """Get logs since the last system boot"""
        return self.get_service_logs(service_name, lines, "last boot")

    def get_service_logs_paginated(self, service_name, page=1, per_page=50, since="24 hours ago"):
        """
        Retrieve paginated logs for a service.
        
        Args:
            service_name (str): Name of the service to query
            page (int): Page number to retrieve (1-based)
            per_page (int): Number of log entries per page
            since (str): Time specification for log retrieval (default: "24 hours ago")
            
        Returns:
            dict: Log data including entries and pagination metadata
        """
        try:
            # URL encode the parameters to handle spaces and special characters
            import urllib.parse
            
            # Build query with pagination parameters
            encoded_since = urllib.parse.quote(since)
            endpoint = f"/services/{service_name}/logs?page={page}&per_page={per_page}&since={encoded_since}"
            
            self.logger.debug(f"Requesting paginated logs with endpoint: {endpoint}")
            
            # Send request to server
            response = self._make_request('GET', endpoint)
            
            # Check for errors
            if "error" in response and response["error"]:
                self.logger.warning(f"Server reported error for {service_name} logs: {response['error']}")
            
            return response
        except Exception as e:
            self.logger.error(f"Error retrieving paginated logs for {service_name}: {e}")
            # Return a valid response even in case of error
            return {
                "service": service_name,
                "error": str(e),
                "log_count": 0,
                "logs": [],
                "pagination": {
                    "page": page,
                    "per_page": per_page,
                    "total_logs": 0,
                    "total_pages": 1, 
                    "has_prev": False,
                    "has_next": False
                }
            }

    # Resource Manager Health Check
    def check_server_health(self):
        """
        Check the health status of the resource manager server.
        
        Returns:
            dict: Health status information
        """
        try:
            return self._make_request('GET', '/health')
        except Exception as e:
            self.logger.error(f"Health check failed: {e}")
            return {
                "status": "unreachable",
                "error": str(e),
                "timestamp": datetime.datetime.now().isoformat()
            }

    # Bulk status methods
    def get_all_services_running_status(self):
        """
        Get the running status for all services.
        
        Returns:
            dict: Dictionary mapping service names to boolean running status
        """
        all_statuses = self.get_all_services_status()
        return {
            service_name: status.get("running", False)
            for service_name, status in all_statuses.items()
        }
    
    def get_all_services_boot_status(self):
        """
        Get the boot status (enabled/disabled) for all services.
        
        Returns:
            dict: Dictionary mapping service names to boolean enabled status
        """
        all_statuses = self.get_all_services_status()
        boot_statuses = {}
        
        for service_name, status in all_statuses.items():
            boot_statuses[service_name] = status.get("enabled", False)
                
        return boot_statuses
    
    def get_all_services_status(self):
        """
        Retrieve raw status of all configured services.
        
        Returns:
            dict: Dictionary mapping service names to their raw status
        """
        return self._make_request('GET', '/services/status')

    # Controlling multiple services
    def restart_services(self, service_names):
        """
        Restart multiple services in sequence.
        
        Args:
            service_names (list): List of service names to restart
            
        Returns:
            dict: Dictionary mapping service names to success/failure status
        """
        results = {}
        for service in service_names:
            try:
                result = self._make_request('POST', f'/services/{service}/restart')
                results[service] = {"success": True, "message": result.get("message", "")}
            except Exception as e:
                self.logger.error(f"Failed to restart {service}: {e}")
                results[service] = {"success": False, "error": str(e)}
        return results

    def stop_all_services(self):
        """
        Stop all available services.
        
        Returns:
            dict: Dictionary mapping service names to success/failure status
        """
        services = self.list_services()
        results = {}
        for service in services:
            try:
                result = self._make_request('POST', f'/services/{service}/stop')
                results[service] = {"success": True, "message": result.get("message", "")}
            except Exception as e:
                self.logger.error(f"Failed to stop {service}: {e}")
                results[service] = {"success": False, "error": str(e)}
        return results

    # Control methods
    def start_service(self, service_name):
        """
        Start the specified service.
        
        This method starts a systemd service and waits until it is confirmed to be running.
        If the service fails to start within the configured timeout, an exception is raised.
        
        Args:
            service_name (str): Name of the service to start
                
        Returns:
            dict: Response message from the server
            
        Raises:
            requests.exceptions.HTTPError: If the service cannot be started
            requests.exceptions.Timeout: If the request times out
        """
        self.logger.info(f"Starting service: {service_name}")
        return self._make_request('POST', f'/services/{service_name}/start')
    
    def stop_service(self, service_name):
        """
        Stop the specified service.
        
        Args:
            service_name (str): Name of the service to stop
            
        Returns:
            dict: Response message from the server
        """
        return self._make_request('POST', f'/services/{service_name}/stop')
    
    def enable_service(self, service_name):
        """
        Enable the service to start on boot.
        
        Args:
            service_name (str): Name of the service to enable
            
        Returns:
            dict: Response message from the server
        """
        return self._make_request('POST', f'/services/{service_name}/enable')
    
    def disable_service(self, service_name):
        """
        Disable the service from starting on boot.
        
        Args:
            service_name (str): Name of the service to disable
            
        Returns:
            dict: Response message from the server
        """
        return self._make_request('POST', f'/services/{service_name}/disable')
    
    def restart_service(self, service_name):
        """
        Restart the specified service.
        
        This method restarts a systemd service and waits until it is confirmed to be running.
        If the service fails to restart within the configured timeout, an exception is raised.
        
        Args:
            service_name (str): Name of the service to start
                
        Returns:
            dict: Response message from the server
            
        Raises:
            requests.exceptions.HTTPError: If the service cannot be restarted
            requests.exceptions.Timeout: If the request times out
        """
        return self._make_request('POST', f'/services/{service_name}/restart')

    def reload_service(self, service_name):
        """
        Reload the specified service.
        
        This method reloads a systemd service and waits until it is confirmed to be running.
        If the service fails to reload within the configured timeout, an exception is raised.
        
        Args:
            service_name (str): Name of the service to reload
                
        Returns:
            dict: Response message from the server
            
        Raises:
            requests.exceptions.HTTPError: If the service cannot be reloaded
            requests.exceptions.Timeout: If the request times out
        """
        return self._make_request('POST', f'/services/{service_name}/reload')

    # Convenience method for comprehensive status
    def get_service_summary(self, service_name):
        """
        Get a summarized view of a service's status with boolean indicators.
        
        Args:
            service_name (str): Name of the service to query
            
        Returns:
            dict: Dictionary with service information including boolean flags
        """
        status = self.get_service_status(service_name)
        
        return {
            "name": service_name,
            "is_running": status.get("running", False),
            "is_enabled": status.get("enabled", False),
            "boot_status": status.get("boot_status", "unknown"),
            "state": status.get("active_raw", ""),
            "config": status.get("loaded_raw", "")
        }