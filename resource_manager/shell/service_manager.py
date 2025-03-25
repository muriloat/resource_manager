from ..client.services.service_controller import ServiceController
import threading
import time
import logging

class ShellServiceManager(ServiceController):
    """Extended service manager with shell-specific functionality."""
    
    def __init__(self, config, logger=None, full_config=None):
        """Initialize the service manager.
        
        Args:
            config: Dictionary with basic connection settings
            logger: Logger instance
            full_config: Full configuration object for multi-server support
        """
        # Create a dedicated logger for this service manager
        if logger:
            self.logger = logger.getChild(f"manager.{config.get('BASE_URL', 'unknown')}")
        else:
            self.logger = logging.getLogger(f"shell_manager.service_manager")
            
        # Initialize the base ServiceController with client parameters
        super().__init__(
            base_url=config.get('BASE_URL'), 
            timeout=config.get('TIMEOUT'),
            logger=self.logger
        )
        
        # Store additional configuration
        self.config = config
        self.full_config = full_config
        
        # Service tracking data structures
        self.services = []
        self.service_data = {}
        self.running_status = {}
        self.boot_status = {}
        self.metadata = {}
        self.resources = {}
        
        # Refresh tracking
        self.last_refresh = 0
        self.refresh_thread = None
        self.should_refresh = True
        self.filter_text = ""
        
        self.logger.debug(f"ShellServiceManager initialized for {config.get('BASE_URL', 'unknown')}")

        # Multi-server data structures
        self.all_servers = {}  # server_id -> ServiceController instances
        self.all_services = {}  # server_id -> list of services
        self.all_statuses = {}  # (server_id, service) -> status dict
        
        # Initialize controllers for all servers
        if full_config:
            self._initialize_all_servers()

    def _initialize_all_servers(self):
        """Initialize service controllers for all configured servers."""
        # Get all host configurations
        try:
            hosts = {}
            if hasattr(self.full_config, 'get_all_hosts'):
                hosts = self.full_config.get_all_hosts()
                self.logger.debug(f"Found {len(hosts)} hosts in configuration")
            else:
                # Fallback for simple config
                hosts = {"default": self.config}
                self.logger.debug("Using fallback single host configuration")
                
            self.logger.debug(f"Initializing controllers for {len(hosts)} servers")
            
            # Create a controller for each host
            for host_id, host_config in hosts.items():
                # Skip if no base URL or internal config items
                if not isinstance(host_config, dict) or host_id.startswith('_') or 'base_url' not in host_config:
                    self.logger.debug(f"Skipping host {host_id}: not a valid host config")
                    continue 

                try:
                    # Create a ServiceController for this host
                    controller = ServiceController(
                        base_url=host_config.get('base_url'),
                        timeout=host_config.get('timeout', 10),
                        logger=self.logger.getChild(f"controller.{host_id}")
                    )
                    
                    # Test connection
                    try:
                        health = controller.check_server_health()
                        is_healthy = health.get('status') == 'healthy'
                        self.logger.debug(f"Health check for {host_id}: {'healthy' if is_healthy else 'unhealthy'}")
                        
                        # Store the controller even if not healthy - we'll handle this during data retrieval
                        self.all_servers[host_id] = controller
                        
                        # Store a reachability flag to avoid timeout errors later
                        if 'error' in health:
                            self.logger.warning(f"Host {host_id} has connection issues: {health.get('error')}")
                            self.all_servers[host_id].is_reachable = False
                        else:
                            self.all_servers[host_id].is_reachable = True
                            
                    except Exception as e:
                        self.logger.warning(f"Health check failed for {host_id}: {e}")
                        # Still store the controller but mark it as unreachable
                        self.all_servers[host_id] = controller
                        self.all_servers[host_id].is_reachable = False
                        
                    self.logger.debug(f"Initialized controller for {host_id}: {host_config.get('base_url')}")
                except Exception as e:
                    self.logger.error(f"Failed to initialize controller for {host_id}: {e}")

            self.logger.debug(f"Successfully initialized {len(self.all_servers)} server controllers")
        except Exception as e:
            self.logger.error(f"Error in server initialization: {e}", exc_info=True)

    def _load_all_servers_data(self):
        """Load data from all configured servers."""
        # Clear previous multi-server data
        self.all_services = {}
        self.all_statuses = {}

        self.logger.debug(f"Loading data from {len(self.all_servers)} servers")
        
        # Process each server
        for server_id, controller in self.all_servers.items():
            try:
                # Skip unreachable hosts with a placeholder entry
                if hasattr(controller, 'is_reachable') and not controller.is_reachable:
                    self.logger.debug(f"Skipping data loading for unreachable host {server_id}")
                    # Add an empty services list for the server
                    self.all_services[server_id] = []
                    continue
                    
                self.logger.debug(f"Loading services from {server_id}")
                
                # Get list of services with timeout handling
                try:
                    services = controller.list_services()
                    self.logger.debug(f"Retrieved {len(services)} services from {server_id}")
                    self.all_services[server_id] = services
                    
                    # Get status for all services
                    running_status = controller.get_all_services_running_status()
                    boot_status = controller.get_all_services_boot_status()
                    
                    # Store combined status
                    for service in services:
                        status_key = (server_id, service)
                        self.all_statuses[status_key] = {
                            "running": running_status.get(service, False),
                            "enabled": boot_status.get(service, False),
                            "metadata": controller.get_service_metadata(service),
                            "resources": {}
                        }
                        
                        # Get resource usage for running services
                        if running_status.get(service, False):
                            try:
                                self.all_statuses[status_key]["resources"] = \
                                    controller.get_service_resource_usage(service)
                            except Exception as e:
                                self.logger.error(f"Error getting resources for {service} on {server_id}: {e}")
                    
                    self.logger.debug(f"Loaded data for {server_id}: {len(services)} services")
                except Exception as e:
                    # If any error occurs, mark the server as unreachable for future requests
                    controller.is_reachable = False
                    self.all_services[server_id] = []  # Empty list instead of None
                    self.logger.error(f"Error retrieving services from {server_id}, marking as unreachable: {e}")
                    
            except Exception as e:
                self.all_services[server_id] = []  # Ensure we have an empty list not None
                self.logger.error(f"Error loading data for server {server_id}: {e}", exc_info=True)
        
        # Log summary of loaded data
        total_services = sum(len(services) for services in self.all_services.values())
        self.logger.debug(f"Total services loaded from all servers: {total_services}")
        self.logger.debug(f"Services by server: {', '.join(f'{k}:{len(v)}' for k, v in self.all_services.items())}")

    def get_combined_services(self):
        """Get a list of all services from all servers with their server ID.
        
        Returns:
            list: List of (server_id, service_name) tuples
        """
        combined = []
        for server_id, services in self.all_services.items():
            # Ensure services is a list
            if services is None:
                continue
            if not isinstance(services, list):
                try:
                    self.logger.error(f"Invalid services data for {server_id}: {type(services)} - {services}")
                    continue
                except Exception:
                    continue
                
            for service in services:
                combined.append((server_id, service))
        self.logger.debug(f"Combined services: {len(combined)} services from {len(self.all_services)} servers")        
        return combined
    
    def get_service_status(self, server_id, service):
        """Get status information for a service on a specific server."""
        status_key = (server_id, service)
        return self.all_statuses.get(status_key, {})

    def log(self, level, message):
        """Log a message if logger is available."""
        if self.logger:
            level_method = getattr(self.logger, level.lower(), None)
            if level_method:
                level_method(message)
        
    def load_all_data(self):
        """Load data from all configured servers."""
        try:
            # Load data for the active server (for backward compatibility)
            success = self._load_active_server_data()
            
            # Load data from all servers
            self._load_all_servers_data()
            
            return success
        except Exception as e:
            self.logger.error(f"Error loading data: {e}")
            return False

    def _load_active_server_data(self):
        """Load all service data in parallel."""
        try:
            # Log attempt
            self.log("debug", "Loading service data")

            # Basic service data - with improved error handling
            try:
                self.services = self.list_services()
                if isinstance(self.services, dict) and "error" in self.services:
                    self.is_reachable = False
                    error_msg = self.services.get("message", "Unknown error")
                    self.logger.error(f"Error listing services: {error_msg}")
                    # Return empty data but don't fail
                    self.services = []
                    self.running_status = {}
                    self.boot_status = {}
                    return False
            except Exception as e:
                self.is_reachable = False
                self.logger.error(f"Failed to list services: {e}")
                self.services = []
                self.running_status = {}
                self.boot_status = {}
                return False

            # Get running and boot status with error handling
            try:
                self.running_status = self.get_all_services_running_status() or {}
                self.boot_status = self.get_all_services_boot_status() or {}
            except Exception as e:
                self.logger.error(f"Error getting service statuses: {e}")
                self.running_status = {}
                self.boot_status = {}

            # Load additional data for each service
            for service in self.services:
                try:
                    # Get metadata for service
                    metadata = self.get_service_metadata(service)
                    if isinstance(metadata, dict):
                        self.metadata[service] = metadata
                    else:
                        self.metadata[service] = {}
                    
                    # Get resource usage if service is running
                    if self.running_status.get(service, False):
                        resources = self.get_service_resource_usage(service)
                        if isinstance(resources, dict):
                            self.resources[service] = resources
                        else:
                            self.resources[service] = {}
                    else:
                        self.resources[service] = {}
                        
                except Exception as e:
                    # Continue with next service if one fails
                    self.log("error", f"Error loading data for {service}: {e}")
                    self.metadata[service] = {}
                    self.resources[service] = {}

            self.log("debug", f"Successfully loaded data for {len(self.services)} services")        
            return True
        except Exception as e:
            self.log("error", f"Error loading data: {e}")
            # Mark as unreachable if we can't load data
            self.is_reachable = False
            return False
            
    def start_refresh_thread(self):
        """Start background refresh thread."""
        self.should_refresh = True
        self.refresh_thread = threading.Thread(target=self._refresh_worker)
        self.refresh_thread.daemon = True
        self.refresh_thread.start()
        
    def stop_refresh_thread(self):
        """Stop background refresh thread."""
        self.should_refresh = False
        if self.refresh_thread:
            self.refresh_thread.join(timeout=1)
            
    def _refresh_worker(self):
        """Background worker to refresh data."""
        while self.should_refresh:
            try:
                now = time.time()
                if now - self.last_refresh > self.config.get('REFRESH_INTERVAL', 30):  # Default 30 seconds
                    self.logger.debug("Starting auto-refresh")
                    try:
                        self.load_all_data()
                        self.last_refresh = now
                        self.logger.debug("Auto-refresh completed")
                    except Exception as e:
                        self.log("error", f"Refresh error: {e}")
            except Exception as e:
                self.logger.error(f"Error in refresh worker: {e}")

            time.sleep(1)
            
    def get_filtered_services(self):
        """Return services matching the current filter."""
        if not self.filter_text:
            return self.services
        return [s for s in self.services if self.filter_text.lower() in s.lower()]
    
    def set_filter(self, filter_text):
        """Set the filter text."""
        self.filter_text = filter_text
    
    def get_filter(self):
        """Get the current filter text."""
        return self.filter_text
            
    def toggle_service_running(self, service):
        """Toggle the running state of a service."""
        try:
            if self.running_status.get(service, False):
                result = self.stop_service(service)
                if result.get('success', False):
                    self.running_status[service] = False
            else:
                result = self.start_service(service)
                if result.get('success', False):
                    self.running_status[service] = True
            return True
        except Exception as e:
            self.log("error", f"Error toggling service {service}: {e}")
            return False
            
    def toggle_service_boot(self, service):
        """Toggle the boot state of a service."""
        try:
            if self.boot_status.get(service, False):
                result = self.disable_service(service)
                if result.get('success', False):
                    self.boot_status[service] = False
            else:
                result = self.enable_service(service)
                if result.get('success', False):
                    self.boot_status[service] = True
            return True
        except Exception as e:
            self.log("error", f"Processing toggle boot for {service}: {e}")
            return False
            
    def get_service_logs(self, service):
        """Get logs for a service."""
        try:
            return self.client.get_service_logs(
                service, 
                lines=self.config.get('LOG_LINES', 100), 
                since=self.config.get('LOG_TIME_RANGE', '1h')
            )
        except Exception as e:
            self.log("error", f"Error getting logs for {service}: {e}")
            return {'logs': [{'message': f"Error: {str(e)}"}]}
            
    def get_service_details(self, service):
        """Get detailed information for a service."""
        try:
            details = self.client.get_service_details(service)
            return details
        except Exception as e:
            self.log("error", f"Error getting details for {service}: {e}")
            return {}

    def reload_service(self, service):
        """Reload a service if it supports reload, otherwise show warning.
        
        Args:
            service (str): Name of the service to reload
            
        Returns:
            dict: Result of operation with success flag and appropriate message
        """
        try:
            # First check if the service supports reload
            if not self.service_supports_reload(service):
                self.logger.warning(f"Service {service} does not support reload")
                return {
                    'success': False,
                    'message': f"Service {service} does not support reload operation. Use restart instead."
                }
            
            # If it supports reload, proceed with the operation
            result = super().reload_service(service)
            return result
        except Exception as e:
            self.logger.error(f"Error during reload check for {service}: {e}")
            return {
                'success': False,
                'message': f"Error checking reload capability: {str(e)}"
            }

    def service_supports_reload(self, service):
        """Check if a service supports reload functionality.
        
        Args:
            service (str): Name of the service to check
            
        Returns:
            bool: True if the service supports reload, False otherwise
        """
        try:
            # Get the service configuration
            config = self.get_service_config(service)
            
            # Check for ExecReload in the Service section
            service_section = config.get('config', {}).get('Service', {})
            
            # If ExecReload exists and has a value, reload is supported
            return 'ExecReload' in service_section and bool(service_section['ExecReload'])
        except Exception as e:
            self.logger.error(f"Error checking reload support for {service}: {e}")
            return False  # Assume not supported if there's an error

# Fix check_server_health to always return a dict
def check_server_health(self):
    """Check health status of the server."""
    try:
        result = self.client.check_server_health()
        # Ensure we always return a dict, even if there's an error
        if not isinstance(result, dict):
            return {"status": "unknown", "error": f"Invalid response: {result}"}
        return result
    except Exception as e:
        self.is_reachable = False
        self.logger.error(f"Error checking server health: {e}")
        return {"status": "error", "error": str(e)}
