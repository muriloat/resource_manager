import logging
from ..config import ClientConfig
from ..logging_setup import setup_client_logging
from .ui_config import UIConfig
from .host_manager import HostManager
# Run app from project's root by: python -m resource_manager.client.ui.app
class ResourceManagerApp:
    """Main application class for the Resource Manager UI."""
    
    def __init__(self):
        """Initialize the Resource Manager UI application."""
        # Set up logging
        self.logger = setup_client_logging(log_level="DEBUG")
        self.logger.info("Initializing Resource Manager application")
        
        # Load configuration
        self.client_config = ClientConfig()
        self.ui_config = UIConfig(self.client_config)
        
        # Initialize host manager
        self.host_manager = HostManager(self.client_config)
        
        # Current active host
        self.current_host_id = self.ui_config.get_default_host_id()
        
    # Host management methods
    def get_hosts(self):
        """Get all configured hosts."""
        return self.host_manager.get_hosts()
    
    def add_host(self, host_id, name, base_url, timeout=80):
        """Add a new host."""
        result = self.host_manager.add_host(host_id, name, base_url, timeout)
        if result and len(self.client_config.get_all_hosts()) == 1:
            # If this is the first host, set it as default
            self.ui_config.set_default_host_id(host_id)
            self.current_host_id = host_id
        return result
    
    def update_host(self, host_id, name, base_url, timeout=80):
        """Update an existing host."""
        return self.host_manager.update_host(host_id, name, base_url, timeout)
    
    def remove_host(self, host_id):
        """Remove a host."""
        result = self.host_manager.remove_host(host_id)
        
        # If we removed the current host, switch to another one
        if result and host_id == self.current_host_id:
            hosts = self.client_config.get_all_hosts()
            if hosts:
                self.current_host_id = hosts[0]
                self.ui_config.set_default_host_id(self.current_host_id)
            else:
                self.current_host_id = "default"
                
        return result
    
    def set_current_host(self, host_id):
        """Set the current active host."""
        if host_id in self.client_config.get_all_hosts():
            self.current_host_id = host_id
            self.ui_config.set_default_host_id(host_id)
            return True
        return False
    
    def get_current_host(self):
        """Get the current active host configuration."""
        hosts = self.host_manager.get_hosts()
        for host in hosts:
            if host["id"] == self.current_host_id:
                return host
        
        # Fall back to first host if current is not found
        return hosts[0] if hosts else None
        
    # Service management methods
    def get_services(self, host_id):
        """Get services for a specific host."""
        client = self.host_manager._get_client(host_id)
        if not client:
            return {"error": "Could not connect to host"}
        
        try:
            # Get list of services
            services = client.list_services()
            
            # Check if there was an error
            if isinstance(services, dict) and "error" in services:
                return services
            
            # Get status for each service
            result = []
            service_statuses = client.get_all_services_status()
            
            for service_name in services:
                service_data = {
                    "name": service_name,
                    "running": False,
                    "enabled": False
                }
                
                # Get status if available
                if service_name in service_statuses:
                    status = service_statuses[service_name]
                    service_data["running"] = status.get("running", False)
                    service_data["enabled"] = status.get("enabled", False)
                    
                result.append(service_data)
                
            return result
        except Exception as e:
            self.logger.error(f"Error fetching services for {host_id}: {e}")
            return {"error": str(e)}
    
    def get_service_metadata(self, host_id, service_name):
        """Get metadata for a specific service."""
        client = self.host_manager._get_client(host_id)
        if not client:
            return {"error": "Could not connect to host"}
        
        try:
            # Get service status to extract resource usage
            status = client.get_service_status(service_name)
            
            # Get service metadata
            metadata = client.get_service_metadata(service_name)
            
            # Get service config for additional info
            config = client.get_service_config(service_name)
            
            # Process units for better display
            unit_section = config.get("config", {}).get("Unit", {})
            service_section = config.get("config", {}).get("Service", {})
            
            # Special handling for multi-line ExecStart
            if "ExecStart" in service_section:
                exec_start = service_section["ExecStart"]
                if isinstance(exec_start, str) and "\\\n" in exec_start:
                    # This is a multi-line command, preserve formatting
                    service_section["ExecStart"] = exec_start.replace("\\\n", "\\")
            
            # Extract resource usage from status
            resources = {
                "pid": status.get("details", {}).get("pid", "N/A"),
                "memory": status.get("details", {}).get("memory", {}),
                "cpu_usage": status.get("details", {}).get("cpu_usage", "N/A"),
                "uptime": status.get("uptime", "N/A"),
                "started_at": status.get("started_at", "")
            }
            
            # Ensure the service is running or provide empty resources
            if not status.get("running", False):
                resources = {
                    "pid": "Not running",
                    "memory": {},
                    "cpu_usage": "N/A",
                    "uptime": "N/A",
                    "started_at": ""
                }
            
            return {
                "service": service_name,
                "metadata": metadata,
                "config": {
                    "Unit": unit_section,
                    "Service": service_section
                },
                "resources": resources,
                "status": {
                    "running": status.get("running", False),
                    "enabled": status.get("enabled", False),
                    "active_raw": status.get("active_raw", ""),
                    "loaded_raw": status.get("loaded_raw", "")
                }
            }
        except Exception as e:
            self.logger.error(f"Error fetching metadata for {service_name} on {host_id}: {e}", exc_info=True)
            return {"error": str(e)}
            
    def control_service(self, host_id, service_name, action):
        """
        Control a service on a specific host.
        
        Args:
            host_id (str): Host identifier
            service_name (str): Service name
            action (str): One of 'start', 'stop', 'enable', 'disable', 'restart'
            
        Returns:
            dict: Result of the operation
        """
        client = self.host_manager._get_client(host_id)
        if not client:
            return {"success": False, "message": "Could not connect to host"}
            
        try:
            # Call appropriate method based on action
            if action == "start":
                result = client.start_service(service_name)
            elif action == "stop":
                result = client.stop_service(service_name)
            elif action == "enable":
                result = client.enable_service(service_name)
            elif action == "disable":
                result = client.disable_service(service_name)
            elif action == "restart":
                result = client.restart_service(service_name)
            else:
                return {"success": False, "message": f"Unknown action: {action}"}
                
            # Check result
            if isinstance(result, dict) and "error" in result:
                return {"success": False, "message": result.get("message", "Operation failed")}
                
            return {"success": True, "message": f"Service {action} successful"}
        except Exception as e:
            self.logger.error(f"Error controlling service {service_name} ({action}): {e}")
            return {"success": False, "message": str(e)}
            
    def get_service_logs(self, host_id, service_name, lines=50):
        """Get logs for a specific service."""
        client = self.host_manager._get_client(host_id)
        if not client:
            return {"error": "Could not connect to host"}
        
        try:
            logs = client.get_service_logs(service_name, lines=lines)
            return logs
        except Exception as e:
            self.logger.error(f"Error fetching logs for {service_name} on {host_id}: {e}")
            return {"error": str(e)}

# Flask application setup
if __name__ == "__main__":
    import sys
    import os
    from flask import Flask, render_template, jsonify, request, redirect, url_for
    
    # Create Flask app with static folder configured
    template_folder = os.path.join(os.path.dirname(__file__), 'templates')
    static_folder = os.path.join(os.path.dirname(__file__), 'static')
    
    app = Flask(__name__, 
                template_folder=template_folder,
                static_folder=static_folder)
    
    resource_manager = ResourceManagerApp()
    
    # Host management routes
    @app.route('/')
    def index():
        hosts = resource_manager.get_hosts()
        return render_template('index.html', hosts=hosts)
    
    @app.route('/api/hosts', methods=['GET'])
    def get_hosts():
        return jsonify(resource_manager.get_hosts())
    
    @app.route('/api/hosts', methods=['POST'])
    def add_host():
        data = request.json
        result = resource_manager.add_host(
            data.get('id'), 
            data.get('name'), 
            data.get('url'),
            int(data.get('timeout', 80))
        )
        return jsonify({"success": result})
    
    @app.route('/api/hosts/<host_id>', methods=['DELETE'])
    def delete_host(host_id):
        result = resource_manager.remove_host(host_id)
        return jsonify({"success": result})
    
    @app.route('/api/hosts/<host_id>', methods=['PUT'])
    def update_host(host_id):
        data = request.json
        result = resource_manager.update_host(
            host_id,
            data.get('name'), 
            data.get('url'),
            int(data.get('timeout', 80))
        )
        return jsonify({"success": result})
    
    @app.route('/api/hosts/<host_id>/test', methods=['POST'])
    def test_host_connection(host_id):
        """Test connection to a host."""
        result = resource_manager.host_manager.test_connection(host_id)
        return jsonify(result)
    
    # Service management routes
    @app.route('/api/hosts/<host_id>/services', methods=['GET'])
    def get_host_services(host_id):
        """Get services for a specific host."""
        services = resource_manager.get_services(host_id)
        
        # Check if there was an error
        if isinstance(services, dict) and "error" in services:
            return jsonify({"error": services["error"]}), 500
            
        return jsonify(services)
    
    @app.route('/api/hosts/<host_id>/services/<service_name>/<action>', methods=['POST'])
    def control_service(host_id, service_name, action):
        """Control a service on a specific host."""
        if action not in ['start', 'stop', 'enable', 'disable', 'restart']:
            return jsonify({"success": False, "message": "Invalid action"}), 400
            
        result = resource_manager.control_service(host_id, service_name, action)
        return jsonify(result)
    
    @app.route('/api/hosts/<host_id>/services/<service_name>/metadata')
    def get_service_metadata(host_id, service_name):
        """Get metadata for a specific service."""
        app.logger.info(f"Fetching metadata for service {service_name} on host {host_id}")
        
        metadata = resource_manager.get_service_metadata(host_id, service_name)
        
        # Debug the response
        app.logger.debug(f"Metadata response: {metadata}")
        
        # Check if there was an error
        if isinstance(metadata, dict) and "error" in metadata:
            app.logger.error(f"Error getting metadata: {metadata['error']}")
            return jsonify({"error": metadata["error"]}), 500
            
        return jsonify(metadata)
    
    @app.route('/api/hosts/<host_id>/services/<service_name>/logs', methods=['GET'])
    def get_service_logs(host_id, service_name):
        """Get logs for a specific service."""
        app.logger.info(f"Fetching logs for {service_name} on host {host_id}")
        
        try:
            # Get pagination parameters if available
            lines = request.args.get('lines', 50, type=int)
            page = request.args.get('page', 1, type=int)
            per_page = request.args.get('per_page', 50, type=int)
            since = request.args.get('since', '24 hours ago')  # Updated default
            
            app.logger.debug(f"Log request with page={page}, per_page={per_page}, lines={lines}")
            
            # Get a client instance
            client = resource_manager.host_manager._get_client(host_id)
            if not client:
                return jsonify({"error": "Could not connect to host", "service": service_name}), 500
            
            # Use the paginated method if pagination parameters are provided
            if 'page' in request.args or 'per_page' in request.args:
                app.logger.info(f"Using paginated logs retrieval for {service_name}: page={page}, per_page={per_page}")
                # Use ServiceController instead of direct client if available
                if hasattr(client, 'get_service_logs_paginated'):
                    logs = client.get_service_logs_paginated(service_name, page=page, per_page=per_page, since=since)
                else:
                    # Create a ServiceController instance
                    from ..services.service_controller import ServiceController
                    service_controller = ServiceController(client=client)
                    logs = service_controller.get_service_logs_paginated(service_name, page=page, per_page=per_page, since=since)
            else:
                # Fall back to non-paginated method for backward compatibility
                logs = resource_manager.get_service_logs(host_id, service_name, lines)
            
            # Debug log the response
            app.logger.debug(f"Logs response structure: {type(logs)}")
            if isinstance(logs, dict):
                app.logger.debug(f"Logs keys: {list(logs.keys())}")
                if 'pagination' in logs:
                    app.logger.info(f"Pagination data: {logs['pagination']}")
            
            # Handle errors or invalid response formats
            if isinstance(logs, dict) and "error" in logs and logs["error"]:
                app.logger.error(f"Error getting logs: {logs['error']}")
                return jsonify({"error": logs["error"], "service": service_name}), 500
                
            if not isinstance(logs, dict) or "logs" not in logs:
                app.logger.warning(f"Invalid logs response format: {logs}")
                return jsonify({
                    "service": service_name,
                    "logs": [],
                    "error": "Invalid response format from server"
                }), 500
                
            # Prepare the response
            response = {
                "service": service_name,
                "logs": logs.get("logs", []),
                "log_count": logs.get("log_count", 0),
                "command": logs.get("command", ""),
                "exit_code": logs.get("exit_code", None),
                "error": logs.get("error", None)
            }
            
            # Include pagination data if available
            if "pagination" in logs:
                response["pagination"] = logs["pagination"]
                app.logger.info(f"Sending pagination in response: {response['pagination']}")
                
            return jsonify(response)
            
        except Exception as e:
            app.logger.exception(f"Exception while fetching logs for {service_name}: {e}")
            return jsonify({
                "service": service_name, 
                "error": str(e), 
                "logs": []
            }), 500
    
    # Host view route
    @app.route('/host/<host_id>')
    def view_host(host_id):
        # Set the current host
        success = resource_manager.set_current_host(host_id)
        if not success:
            return redirect(url_for('index'))
            
        # Get host details
        host = resource_manager.get_current_host()
        return render_template('host_view.html', host=host)
    
    # Run the application
    print("Starting Resource Manager UI...")
    app.run(debug=True, host='0.0.0.0', port=8080)
