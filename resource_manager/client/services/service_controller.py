import logging

class ServiceController:
    """Core service management functionality without UI dependencies."""
    
    def __init__(self, client=None, base_url=None, timeout=None, logger=None):
        # Get or create a logger
        self.logger = logger or logging.getLogger("resource_manager.controller")

        if client:
            self.client = client
        else:
            from ...client.resource_manager_client import ResourceManagerClient
            self.client = ResourceManagerClient(base_url=base_url, timeout=timeout)

            # If the client has a logger, use it for more detailed debugging
            if hasattr(self.client, 'logger'):
                self.client.logger = self.logger

        self.logger.debug("ServiceController initialized")
        
    def get_services(self):
        """Get list of all services."""
        return self.client.list_services()
    
    def list_services(self):
        """Get list of all services."""
        return self.client.list_services()
        
    def get_service_status(self, service):
        """Get running and boot status for a service."""
        return {
            'is_running': self.client.is_service_running(service),
            'is_enabled': self.client.is_service_enabled(service)
        }
    
    def is_service_running(self, service):
        """Check if a service is currently running."""
        return self.client.is_service_running(service)
    
    def is_service_enabled(self, service):
        """Check if a service is enabled at boot."""
        return self.client.is_service_enabled(service)
    
    def get_all_services_status(self):
        """Get status for all services."""
        return self.client.get_all_services_status()
    
    def get_all_services_running_status(self):
        """Get running status for all services."""
        return self.client.get_all_services_running_status()
    
    def get_all_services_boot_status(self):
        """Get boot status for all services."""
        return self.client.get_all_services_boot_status()
    
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
        
    # Configuration and metadata methods
    def get_service_config(self, service):
        """Get configuration for a service."""
        return self.client.get_service_config(service)

    def get_service_metadata(self, service):
        """Get metadata for a service."""
        return self.client.get_service_metadata(service)   


    def get_service_metadata_old(self, service):
        """Extract clean metadata from service config."""
        try:
            self.logger.debug(f"Getting metadata for service: {service}")
            config = self.client.get_service_config(service)

            # Log the raw metadata
            self.logger.debug(f"Raw config for {service}: {config}")
            self.logger.debug(f"Raw metadata for {service}: {config.get('metadata', {})}")

            metadata_dict = {}
            
            for key, value in config.get('metadata', {}).items():
                if key.startswith('X-Metadata-'):
                    metadata_key = key.replace('X-Metadata-', '')
                    metadata_dict[metadata_key] = value

            # Log the processed metadata
            self.logger.debug(f"Processed metadata for {service}: {metadata_dict}")
                    
            return metadata_dict
        except Exception as e:
            self.logger.error(f"Error getting metadata for {service}: {e}", exc_info=True)
            return {}

    # Resource usage methods
    def get_service_resource_usage(self, service):
        """Get resource usage for a service."""
        return self.client.get_service_resource_usage(service)        

    def get_service_resources(self, service):
        """Get resource usage for a service if it's running."""
        try:
            if self.client.is_service_running(service):
                return self.client.get_service_resource_usage(service)
            return {}
        except Exception:
            return {}
            
    # Core service control methods
    def start_service(self, service):
        return self.client.start_service(service)

    def stop_service(self, service):
        return self.client.stop_service(service)
    
    def restart_service(self, service):
        return self.client.restart_service(service)
    
    def reload_service(self, service):
        return self.client.reload_service(service)
        
    def enable_service(self, service):
        return self.client.enable_service(service)
        
    def disable_service(self, service):
        return self.client.disable_service(service)
        
    # Server health methods
    def check_server_health(self):
        """Check health status of the server."""
        return self.client.check_server_health()
    
    # Batch operations
    def get_services_by_status(self, running=True):
        """Get a list of services with specified running status."""
        running_status = self.get_all_services_running_status()
        return [s for s, status in running_status.items() if status == running]
    
    def get_services_by_boot_status(self, enabled=True):
        """Get a list of services with specified boot status."""
        boot_status = self.get_all_services_boot_status()
        return [s for s, status in boot_status.items() if status == enabled]
    
    # Enhanced information methods
    def get_service_summary(self, service):
        """Get a summary of service information including status, config, and resources."""
        try:
            summary = {
                'service': service,
                'status': self.get_service_status(service),
                'metadata': self.get_service_metadata(service)
            }
            
            # Add resources if service is running
            if summary['status']['is_running']:
                summary['resources'] = self.get_service_resource_usage(service)
            else:
                summary['resources'] = {}
                
            return summary
        except Exception:
            return {'service': service, 'error': 'Failed to retrieve service information'}
    
    def get_multiple_services_summary(self, services):
        """Get summary information for multiple services."""
        return {service: self.get_service_summary(service) for service in services}

    def get_service_logs(self, service, lines=50):
        """Get logs for a service. (Legacy method - no pagination)"""
        return self.client.get_service_logs(service, lines=lines)

    def get_service_logs_paginated(self, service, page=1, per_page=50, since="24 hours ago"):
        """Get paginated logs for a service.
        
        Args:
            service (str): Name of the service to get logs for
            page (int): Page number (1-based)
            per_page (int): Number of log entries per page
            since (str): Time specification for log retrieval
            
        Returns:
            dict: Dictionary containing logs and pagination metadata
        """
        self.logger.debug(f"Getting paginated logs for {service}: page={page}, per_page={per_page}")
        
        # Check if the client's API supports pagination directly
        if hasattr(self.client, 'get_service_logs_paginated'):
            return self.client.get_service_logs_paginated(service, page=page, per_page=per_page, since=since)
            
        # If not, we need to modify our request to achieve pagination
        # Build a query string for the backend API that includes pagination
        logs = self.client._make_request(
            'GET', 
            f"/services/{service}/logs?page={page}&per_page={per_page}&since={since}"
        )
        
        # If the response doesn't include pagination data, add it based on our request parameters
        if logs and 'pagination' not in logs:
            logs['pagination'] = {
                'page': page,
                'per_page': per_page,
                'total_logs': len(logs.get('logs', [])),
                'total_pages': 1,  # Assume 1 page if server doesn't provide this
                'has_prev': page > 1,
                'has_next': False  # Can't determine without knowing total
            }
            
        return logs