#!/usr/bin/env python3
# Service Management server to manage services on a Linux system.
# The server uses systemctl to start, stop, enable, and disable services.
# It also provides a way to check the status of services.
# The server is configured with a dictionary of services, where each service
# has a name and optional configuration for start/stop timeouts and start strings.
# The server is intended to be used with the client in the resource_manager package.
# The server is not secure and should not be exposed to the internet.
# Refer to https://github.com/muriloat/resource_manager for more information.

import subprocess, time, datetime, re, os, json
from flask import Flask, jsonify, abort
from services_config import services_config
from fixed_pagination import get_paginated_journal_logs
version="1.0.1"

# Get the directory where this script is located
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__)

# Helper functions
def run_command(command):
    """Helper to run a subprocess command."""
    try:
        result = subprocess.run(command, capture_output=True, text=True)
        return result.stdout, result.stderr, result.returncode
    except Exception as e:
        return "", str(e), 1

def get_service_status(service_name):
    """Get detailed status of a service with parsed metrics."""
    stdout, stderr, code = run_command(["sudo", "systemctl", "status", f"{service_name}.service"])
    
    # Initialize with basic structure
    parsed_data = {
        "service": service_name,
        "running": False,
        "enabled": False,
        "details": {}
    }
    
    # Check if service exists, even if not running
    loaded_check, _, _ = run_command(["sudo", "systemctl", "show", f"{service_name}.service", "--property=LoadState"])
    if "not-found" in loaded_check.lower():
        return {"error": f"Service {service_name} not found"}
    
    # Check for enabled status even if service isn't running
    enabled_check, _, _ = run_command(["sudo", "systemctl", "is-enabled", f"{service_name}.service"])
    parsed_data["enabled"] = "enabled" in enabled_check.lower()
    parsed_data["boot_status"] = enabled_check.strip()
    
    # If service is not running, systemctl status returns non-zero
    # But we still want to provide some basic info
    if code != 0:
        parsed_data["running"] = False
        parsed_data["active_raw"] = "inactive"
        return parsed_data
    
    # If we got here, service exists and has status output to parse
    # Extract status information
    active_match = re.search(r"Active:\s+([^\n]+)", stdout)
    loaded_match = re.search(r"Loaded:\s+([^\n]+)", stdout)
    
    # Parse running status
    if active_match:
        active_status = active_match.group(1).strip()
        parsed_data["active_raw"] = active_status
        parsed_data["running"] = "running" in active_status.lower()
        
        # Extract timestamp and uptime
        timestamp_match = re.search(r"since (.+?);(.+?)ago", active_status)
        if timestamp_match:
            parsed_data["started_at"] = timestamp_match.group(1).strip()
            parsed_data["uptime"] = timestamp_match.group(2).strip()
    
    # Parse boot status
    if loaded_match:
        loaded_status = loaded_match.group(1).strip()
        parsed_data["loaded_raw"] = loaded_status
        enabled_match = re.search(r";\s*(enabled|disabled|indirect|static)", loaded_status)
        if enabled_match:
            boot_status = enabled_match.group(1).lower()
            parsed_data["enabled"] = boot_status in ["enabled", "indirect"]
            parsed_data["boot_status"] = boot_status
    
    # Extract process details if running
    pid_match = re.search(r"Main PID: (\d+)", stdout)
    if pid_match:
        parsed_data["details"]["pid"] = int(pid_match.group(1))
    
    tasks_match = re.search(r"Tasks: (\d+) \(limit: (\d+)\)", stdout)
    if tasks_match:
        parsed_data["details"]["tasks"] = {
            "current": int(tasks_match.group(1)),
            "limit": int(tasks_match.group(2))
        }
    
    memory_match = re.search(r"Memory: ([^(]+)\(peak: ([^)]+)\)", stdout)
    if memory_match:
        parsed_data["details"]["memory"] = {
            "current": memory_match.group(1).strip(),
            "peak": memory_match.group(2).strip()
        }
    
    cpu_match = re.search(r"CPU: ([^\n]+)", stdout)
    if cpu_match:
        parsed_data["details"]["cpu_usage"] = cpu_match.group(1).strip()
    
    return parsed_data

def wait_for_stop(service_name, timeout):
    """Polls systemctl is-active until the service reports inactive or timeout is reached."""
    return _wait_for_service_state(service_name, "inactive", timeout)

def wait_for_start(service_name, timeout):
    """Polls systemctl is-active until the service reports active or timeout is reached."""
    return _wait_for_service_state(service_name, "active", timeout)

def _wait_for_service_state(service_name, desired_state, timeout):
    """Generic method to poll for a specific service state."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        stdout, _, _ = run_command(["sudo", "systemctl", "is-active", f"{service_name}.service"])
        if stdout.strip() == desired_state:
            return True
        time.sleep(1)
    return False

def wait_for_start_log(service_name, start_string, timeout, since_timestamp):
    """
    Polls the service logs (via journalctl) for a log line that contains the required start_string.
    The search only considers logs since the given timestamp.
    """
    # If no start_string is defined, fall back to the simpler method
    if not start_string:
        return wait_for_start(service_name, timeout)
        
    since_str = datetime.datetime.fromtimestamp(since_timestamp).strftime('%Y-%m-%d %H:%M:%S')
    start_time = time.time()
    while time.time() - start_time < timeout:
        stdout, _, _ = run_command([
            "journalctl", "-u", f"{service_name}.service",
            "--since", since_str, "-n", "50"
        ])
        if start_string in stdout:
            return True
        time.sleep(1)
    return False


# List services
@app.route('/services', methods=['GET'])
def list_services():
    """List all services available (as defined in the configuration)."""
    return jsonify(list(services_config.keys()))

@app.route('/services/summary', methods=['GET'])
def services_summary():
    """Return a summary of service statuses."""
    running_count = 0
    stopped_count = 0
    services_data = []
    
    for service_name in services_config:
        status = get_service_status(service_name)
        is_running = status.get("running", False)
        services_data.append({
            "name": service_name,
            "running": is_running,
            "enabled": status.get("enabled", False)
        })
        if is_running:
            running_count += 1
        else:
            stopped_count += 1
    
    return jsonify({
        "total": len(services_config),
        "running": running_count,
        "stopped": stopped_count,
        "services": services_data
    })

# Status methods
@app.route('/services/status', methods=['GET'])
def all_services_status():
    """Return the status for every service defined in the configuration."""
    statuses = {}
    for service_name in services_config:
        statuses[service_name] = get_service_status(service_name)
    return jsonify(statuses)

@app.route('/services/<service_name>/status', methods=['GET'])
def service_status(service_name):
    """Return the status for a single service."""
    if service_name not in services_config:
        abort(404, description="Service not found")
    status = get_service_status(service_name)
    return jsonify(status)


# Metadata method
@app.route('/services/<service_name>/config', methods=['GET'])
def get_service_config(service_name):
    """Extract and return the configuration of a service from its unit file."""
    if service_name not in services_config:
        abort(404, description="Service not found")
    
    stdout, stderr, code = run_command(["sudo", "systemctl", "cat", f"{service_name}.service"])
    if code != 0:
        abort(500, description=f"Failed to read service file: {stderr}")
    
    # Parse service file content
    sections = {"Unit": {}, "Service": {}, "Install": {}}
    current_section = None
    custom_metadata = {}
    
    for line in stdout.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        
        # Check if this is a section header
        section_match = re.match(r"\[([A-Za-z]+)\]", line)
        if section_match:
            current_section = section_match.group(1)
            continue
        
        if current_section and "=" in line:
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            
            # Clean up escaped quotes if present
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1]  # Remove outermost quotes
            
            # Unescape any internal quotes
            value = value.replace('\\"', '"')
            
            # Handle X-Metadata entries
            if key.startswith("X-Metadata-"):
                metadata_key = key[11:]  # Remove "X-Metadata-" prefix
                custom_metadata[metadata_key] = value
                continue  # Skip adding to section dict since we handle it separately
            
            # Handle multiple Environment entries
            if current_section == "Service" and key == "Environment":
                if "Environment" not in sections["Service"]:
                    sections["Service"]["Environment"] = []
                sections["Service"]["Environment"].append(value)
            else:
                # Regular entries
                sections[current_section][key] = value
    
    return jsonify({
        "service": service_name,
        "config": sections,
        "metadata": custom_metadata
    })


@app.route('/services/<service_name>/logs', methods=['GET'])
def get_service_logs(service_name):
    """Return recent logs for a service with pagination support."""
    from flask import request
    
    if service_name not in services_config:
        abort(404, description="Service not found")
    
    # Get query parameters
    lines = request.args.get('lines', '50')
    since = request.args.get('since', '24 hours ago')
    page = request.args.get('page', '1')
    per_page = request.args.get('per_page', '50')
    
    try:
        # Convert parameters to integers
        page_num = int(page)
        per_page_num = int(per_page)
        lines_num = int(lines)
        
        # Basic validation
        if page_num < 1:
            page_num = 1
        if per_page_num < 1:
            per_page_num = 50
        
        # Use our pagination utility if page parameter is provided
        if 'page' in request.args:
            app.logger.info(f"Using paginated logs retrieval: page={page_num}, per_page={per_page_num}")
            return jsonify(get_paginated_journal_logs(
                service_name, 
                page=page_num,
                per_page=per_page_num,
                since=since
            ))
        
        # Legacy non-paginated approach for backward compatibility
        app.logger.info("Using legacy non-paginated logs retrieval")
        cmd = [
            "sudo", "/usr/bin/journalctl", 
            "-u", f"{service_name}.service",
            "-n", lines
        ]
        
        # Add since parameter if provided
        if since:
            cmd.extend(["--since", since])
            
        # Add no-pager to ensure we get all output
        cmd.append("--no-pager")
        
        app.logger.info(f"Executing command: {' '.join(cmd)}")
        
        # Execute the command
        stdout, stderr, code = run_command(cmd)
        
        if code != 0:
            app.logger.warning(f"journalctl returned non-zero exit code: {code}")
            app.logger.warning(f"stderr: {stderr}")
        
        # Parse logs into structured format
        log_entries = []
        for line in stdout.splitlines():
            # Skip empty lines
            if not line.strip():
                continue
            
            # Add the raw line as a fallback
            log_entry = {"raw": line}
            
            # Try to parse log line
            try:
                # Most journal entries follow format: date time hostname process[pid]: message
                parts = re.match(r"([a-zA-Z]+ \d+ \d+:\d+:\d+) ([^ ]+) ([^:]+): (.*)", line)
                if parts:
                    timestamp, hostname, process, message = parts.groups()
                    log_entry.update({
                        "timestamp": timestamp,
                        "hostname": hostname,
                        "process": process,
                        "message": message
                    })
                else:
                    # Alternative format often used in journalctl
                    alt_parts = re.match(r"([a-zA-Z]{3} \d+ \d+:\d+:\d+) (.+)", line)
                    if alt_parts:
                        timestamp, message = alt_parts.groups()
                        log_entry.update({
                            "timestamp": timestamp,
                            "message": message
                        })
            except Exception as e:
                app.logger.warning(f"Error parsing log line: {e}")
            
            log_entries.append(log_entry)
        
        return jsonify({
            "service": service_name,
            "log_count": len(log_entries),
            "logs": log_entries,
            "command": " ".join(cmd), 
            "exit_code": code,
            "error": stderr if stderr else None
        })
    
    except Exception as e:
        error_msg = f"Error retrieving logs: {str(e)}"
        app.logger.error(error_msg)
        return jsonify({
            "service": service_name,
            "error": error_msg,
            "log_count": 0,
            "logs": []
        }), 500

# Resource Manager Health Check
@app.route('/health', methods=['GET'])
def health_check():
    """Return health status of the resource manager service."""
    # Check for systemd
    _, _, systemd_code = run_command(["sudo", "systemctl", "--version"])
    systemd_ok = systemd_code == 0
    
    # Check if we can access our own status
    own_service = "resource_manager"
    self_status = {}
    
    try:
        if own_service in services_config:
            self_status = get_service_status(own_service)
        else:
            # Try to use process information as a fallback
            pid = os.getpid()
            self_status = {
                "service": own_service,
                "running": True,
                "pid": pid
            }
    except Exception as e:
        self_status = {
            "service": own_service,
            "error": str(e),
            "running": True  
        }
    
    return jsonify({
        "status": "Healthy" if systemd_ok else "Degraded",
        "timestamp": datetime.datetime.now().isoformat(),
        "systemd_available": systemd_ok,
        "self_status": self_status,
        "api_version": version
    })


# Control methods
@app.route('/services/<service_name>/stop', methods=['POST'])
def stop_service(service_name):
    """
    Stop the given service using systemctl, then poll until it is confirmed to be inactive.
    Respond with 200 once the service is fully stopped.
    """
    app.logger.info(f"Received request to stop service: {service_name}")
    
    if service_name not in services_config:
        app.logger.error(f"Service not found: {service_name}")
        abort(404, description="Service not found")
    
    # Check current status before stopping
    pre_status = get_service_status(service_name)
    app.logger.info(f"Pre-stop status of {service_name}: running={pre_status.get('running', False)}")
    
    # If already stopped, return success
    if not pre_status.get('running', False):
        app.logger.info(f"Service {service_name} is already stopped. No action needed.")
        return jsonify({"message": f"{service_name} is already stopped."})
    
    # Issue the stop command
    app.logger.info(f"Executing stop command for {service_name}")
    stop_cmd = ["sudo", "systemctl", "stop", f"{service_name}.service"]
    app.logger.debug(f"Command: {' '.join(stop_cmd)}")
    
    stdout, stderr, code = run_command(stop_cmd)
    app.logger.debug(f"Stop command result: code={code}, stdout={stdout}, stderr={stderr}")
    
    if code != 0:
        app.logger.error(f"Failed to stop {service_name}: {stderr}")
        abort(500, description=f"Failed to stop service: {stderr}")
    
    # Wait for the service to report as inactive
    stop_timeout = services_config[service_name].get("stop_timeout", 20)
    app.logger.info(f"Waiting up to {stop_timeout} seconds for {service_name} to stop")
    
    start_wait = time.time()
    stopped = wait_for_stop(service_name, stop_timeout)
    wait_duration = time.time() - start_wait
    
    if stopped:
        app.logger.info(f"Service {service_name} stopped successfully after {wait_duration:.2f} seconds")
        
        # Verify final status
        post_status = get_service_status(service_name)
        app.logger.info(f"Post-stop status of {service_name}: running={post_status.get('running', False)}")
        
        return jsonify({
            "message": f"{service_name} stopped successfully.",
            "duration": f"{wait_duration:.2f} seconds"
        })
    else:
        app.logger.error(f"Timeout waiting for {service_name} to stop after {wait_duration:.2f} seconds")
        
        # Check final status even after timeout
        post_status = get_service_status(service_name)
        app.logger.error(f"Service status after timeout: running={post_status.get('running', False)}")
        
        abort(500, description=f"Timeout waiting for service to stop after {wait_duration:.2f} seconds")

@app.route('/services/<service_name>/start', methods=['POST'])
def start_service(service_name):
    """
    Start the given service using systemctl and wait until it confirms the service is ready.
    First tries log-based detection for precision, falls back to active state polling if needed.
    """
    app.logger.info(f"Received request to start service: {service_name}")
    
    if service_name not in services_config:
        app.logger.error(f"Service not found: {service_name}")
        abort(404, description="Service not found")
    
    # Check current status before starting
    pre_status = get_service_status(service_name)
    app.logger.info(f"Pre-start status of {service_name}: running={pre_status.get('running', True)}")
    
    # If already running, return success
    if pre_status.get('running', True):
        app.logger.info(f"Service {service_name} is already running. No action needed.")
        return jsonify({"message": f"{service_name} is already running."})
    
    # Record the timestamp so we can search logs only for new messages
    since_timestamp = time.time()
    
    # Issue the start command
    app.logger.info(f"Executing start command for {service_name}")
    start_cmd = ["sudo", "systemctl", "start", f"{service_name}.service"]
    app.logger.debug(f"Command: {' '.join(start_cmd)}")
    
    stdout, stderr, code = run_command(start_cmd)
    app.logger.debug(f"Start command result: code={code}, stdout={stdout}, stderr={stderr}")
    
    if code != 0:
        app.logger.error(f"Failed to start {service_name}: {stderr}")
        abort(500, description=f"Failed to start service: {stderr}")
    
    # Wait for the service to start
    start_timeout = services_config[service_name].get("start_timeout", 20)
    start_string = services_config[service_name].get("start_string")
    
    if start_string:
        app.logger.info(f"Waiting up to {start_timeout} seconds for {service_name} to start with log marker: '{start_string}'")
        start_wait = time.time()
        started = wait_for_start_log(service_name, start_string, start_timeout, since_timestamp)
    else:
        app.logger.info(f"No start string defined for {service_name}, waiting for active state")
        start_wait = time.time()
        started = wait_for_start(service_name, start_timeout)
        
    wait_duration = time.time() - start_wait
    
    # Also check systemctl is-active as a backup
    is_active_stdout, _, _ = run_command(["sudo", "systemctl", "is-active", f"{service_name}.service"])
    is_active = is_active_stdout.strip() == "active"
    
    app.logger.debug(f"Service active status: {is_active_stdout.strip()}")
    
    if started or is_active:
        app.logger.info(f"Service {service_name} started successfully after {wait_duration:.2f} seconds")
        
        # Verify final status
        post_status = get_service_status(service_name)
        app.logger.info(f"Post-start status of {service_name}: running={post_status.get('running', False)}")
        
        return jsonify({
            "message": f"{service_name} started successfully.",
            "duration": f"{wait_duration:.2f} seconds",
            "log_matched": started,
            "is_active": is_active
        })
    else:
        app.logger.error(f"Timeout waiting for {service_name} to start after {wait_duration:.2f} seconds")
        
        # Check final status even after timeout
        post_status = get_service_status(service_name)
        app.logger.error(f"Service status after timeout: running={post_status.get('running', False)}")
        
        # Get recent logs for debugging
        recent_logs_cmd = ["sudo", "journalctl", "-u", f"{service_name}.service", "-n", "10", "--no-pager"]
        logs_stdout, _, _ = run_command(recent_logs_cmd)
        app.logger.error(f"Recent logs for {service_name}:\n{logs_stdout}")
        
        abort(500, description=f"Timeout waiting for service to start after {wait_duration:.2f} seconds")

@app.route('/services/<service_name>/enable', methods=['POST'])
def enable_service(service_name):
    """
    Enable a service so that it starts on boot (using systemctl enable).
    This reflects the 'enabled' configuration.
    """
    app.logger.info(f"Received request to enable service: {service_name}")
    
    if service_name not in services_config:
        app.logger.error(f"Service not found: {service_name}")
        abort(404, description="Service not found")
    
    # Check current enabled status
    pre_status = get_service_status(service_name)
    app.logger.info(f"Pre-enable status of {service_name}: enabled={pre_status.get('enabled', False)}")
    
    # If already enabled, return success
    if pre_status.get('enabled', False):
        app.logger.info(f"Service {service_name} is already enabled. No action needed.")
        return jsonify({"message": f"{service_name} is already enabled."})
    
    # Issue the enable command
    app.logger.info(f"Executing enable command for {service_name}")
    enable_cmd = ["sudo", "systemctl", "enable", f"{service_name}.service"]
    app.logger.debug(f"Command: {' '.join(enable_cmd)}")
    
    stdout, stderr, code = run_command(enable_cmd)
    app.logger.debug(f"Enable command result: code={code}, stdout={stdout}, stderr={stderr}")
    
    if code != 0:
        app.logger.error(f"Failed to enable {service_name}: {stderr}")
        abort(500, description=f"Failed to enable service: {stderr}")
    
    # Verify the service is now enabled
    post_status = get_service_status(service_name)
    is_enabled = post_status.get('enabled', False)
    
    app.logger.info(f"Post-enable status of {service_name}: enabled={is_enabled}")
    
    if is_enabled:
        return jsonify({"message": f"{service_name} enabled successfully."})
    else:
        app.logger.warning(f"Service {service_name} might not be properly enabled despite successful command")
        return jsonify({
            "message": f"{service_name} enable command completed, but verification shows it may not be enabled.",
            "command_output": stdout
        })

@app.route('/services/<service_name>/disable', methods=['POST'])
def disable_service(service_name):
    """
    Disable a service so that it will not start automatically on boot.
    """
    app.logger.info(f"Received request to disable service: {service_name}")
    
    if service_name not in services_config:
        app.logger.error(f"Service not found: {service_name}")
        abort(404, description="Service not found")
    
    # Check current enabled status
    pre_status = get_service_status(service_name)
    app.logger.info(f"Pre-disable status of {service_name}: enabled={pre_status.get('enabled', False)}")
    
    # If already disabled, return success
    if not pre_status.get('enabled', True):
        app.logger.info(f"Service {service_name} is already disabled. No action needed.")
        return jsonify({"message": f"{service_name} is already disabled."})
    
    # Issue the disable command
    app.logger.info(f"Executing disable command for {service_name}")
    disable_cmd = ["sudo", "systemctl", "disable", f"{service_name}.service"]
    app.logger.debug(f"Command: {' '.join(disable_cmd)}")
    
    stdout, stderr, code = run_command(disable_cmd)
    app.logger.debug(f"Disable command result: code={code}, stdout={stdout}, stderr={stderr}")
    
    if code != 0:
        app.logger.error(f"Failed to disable {service_name}: {stderr}")
        abort(500, description=f"Failed to disable service: {stderr}")
    
    # Verify the service is now disabled
    post_status = get_service_status(service_name)
    is_disabled = not post_status.get('enabled', True)
    
    app.logger.info(f"Post-disable status of {service_name}: disabled={is_disabled}")
    
    if is_disabled:
        return jsonify({"message": f"{service_name} disabled successfully."})
    else:
        app.logger.warning(f"Service {service_name} might not be properly disabled despite successful command")
        return jsonify({
            "message": f"{service_name} disable command completed, but verification shows it may still be enabled.",
            "command_output": stdout
        })

@app.route('/services/<service_name>/restart', methods=['POST'])
def restart_service(service_name):
    """Restart a service and wait for it to start up."""
    app.logger.info(f"Received request to restart service: {service_name}")
    
    if service_name not in services_config:
        app.logger.error(f"Service not found: {service_name}")
        abort(404, description="Service not found")
    
    # Check current status before restarting
    pre_status = get_service_status(service_name)
    app.logger.info(f"Pre-restart status of {service_name}: running={pre_status.get('running', False)}")
    
    # Record the timestamp for log monitoring
    since_timestamp = time.time()
    
    # Issue the restart command
    app.logger.info(f"Executing restart command for {service_name}")
    restart_cmd = ["sudo", "systemctl", "restart", f"{service_name}.service"]
    app.logger.debug(f"Command: {' '.join(restart_cmd)}")
    
    stdout, stderr, code = run_command(restart_cmd)
    app.logger.debug(f"Restart command result: code={code}, stdout={stdout}, stderr={stderr}")
    
    if code != 0:
        app.logger.error(f"Failed to restart {service_name}: {stderr}")
        abort(500, description=f"Failed to restart service: {stderr}")
    
    # Wait for the service to start
    start_timeout = services_config[service_name].get("start_timeout", 20)
    start_string = services_config[service_name].get("start_string")
    
    if start_string:
        app.logger.info(f"Waiting up to {start_timeout} seconds for {service_name} to restart with log marker: '{start_string}'")
        start_wait = time.time()
        restarted = wait_for_start_log(service_name, start_string, start_timeout, since_timestamp)
    else:
        app.logger.info(f"No start string defined for {service_name}, waiting for active state")
        start_wait = time.time()
        restarted = wait_for_start(service_name, start_timeout)
        
    wait_duration = time.time() - start_wait
    
    # Also check systemctl is-active as a backup
    is_active_stdout, _, _ = run_command(["sudo", "systemctl", "is-active", f"{service_name}.service"])
    is_active = is_active_stdout.strip() == "active"
    
    app.logger.debug(f"Service active status: {is_active_stdout.strip()}")
    
    if restarted or is_active:
        app.logger.info(f"Service {service_name} restarted successfully after {wait_duration:.2f} seconds")
        
        # Verify final status
        post_status = get_service_status(service_name)
        app.logger.info(f"Post-restart status of {service_name}: running={post_status.get('running', False)}")
        
        return jsonify({
            "message": f"{service_name} restarted successfully.",
            "duration": f"{wait_duration:.2f} seconds",
            "log_matched": restarted,
            "is_active": is_active
        })
    else:
        app.logger.error(f"Timeout waiting for {service_name} to restart after {wait_duration:.2f} seconds")
        
        # Check final status even after timeout
        post_status = get_service_status(service_name)
        app.logger.error(f"Service status after timeout: running={post_status.get('running', False)}")
        
        # Get recent logs for debugging
        recent_logs_cmd = ["sudo", "journalctl", "-u", f"{service_name}.service", "-n", "10", "--no-pager"]
        logs_stdout, _, _ = run_command(recent_logs_cmd)
        app.logger.error(f"Recent logs for {service_name}:\n{logs_stdout}")
        
        abort(500, description=f"Timeout waiting for service to restart after {wait_duration:.2f} seconds")

@app.route('/services/<service_name>/reload', methods=['POST'])
def reload_service(service_name):
    """Reload a service configuration without restarting it."""
    app.logger.info(f"Received request to reload service: {service_name}")
    
    if service_name not in services_config:
        app.logger.error(f"Service not found: {service_name}")
        abort(404, description="Service not found")
    
    # Check current status before reloading
    pre_status = get_service_status(service_name)
    app.logger.info(f"Pre-reload status of {service_name}: running={pre_status.get('running', False)}")
    
    # If not running, can't reload
    if not pre_status.get('running', False):
        app.logger.warning(f"Service {service_name} is not running, cannot reload.")
        abort(400, description=f"Service {service_name} is not running. Cannot reload a stopped service.")
    
    # Issue the reload command
    app.logger.info(f"Executing reload command for {service_name}")
    reload_cmd = ["sudo", "systemctl", "reload", f"{service_name}.service"]
    app.logger.debug(f"Command: {' '.join(reload_cmd)}")
    
    stdout, stderr, code = run_command(reload_cmd)
    app.logger.debug(f"Reload command result: code={code}, stdout={stdout}, stderr={stderr}")
    
    if code != 0:
        app.logger.error(f"Failed to reload {service_name}: {stderr}")
        
        # Check if this is because the service doesn't support reload
        if "not found" in stderr or "reload" in stderr:
            app.logger.warning(f"Service {service_name} does not support reload operation")
            abort(400, description=f"Service {service_name} does not support reload operation. Try restart instead.")
        else:
            abort(500, description=f"Failed to reload service: {stderr}")
    
    # Verify final status
    post_status = get_service_status(service_name)
    app.logger.info(f"Post-reload status of {service_name}: running={post_status.get('running', False)}")
    
    return jsonify({
        "message": f"{service_name} configuration reloaded successfully."
    })

# System Information Routes

@app.route('/system/info', methods=['GET'])
def get_all_system_info():
    """Return all system information."""
    try:
        script_path = os.path.join(SCRIPT_DIR, "get_detailed.sh")
        stdout, stderr, code = run_command(["sudo", script_path, "all"])
        if code != 0:
            return jsonify({"error": f"Failed to get system information: {stderr}"}), 500
        
        # The 'all' command writes to a file, so we need to read that file
        try:
            with open('/opt/resource_manager/static_info.json', 'r') as f:
                data = json.load(f)
                return jsonify(data)
        except Exception as e:
            return jsonify({"error": f"Failed to read system information file: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"error": f"Failed to execute system information script: {str(e)}"}), 500

@app.route('/system/os', methods=['GET'])
def get_os_info():
    """Return operating system information."""
    return _execute_detailed_script("os_info")

@app.route('/system/cpu', methods=['GET'])
def get_cpu_info():
    """Return CPU information."""
    return _execute_detailed_script("cpu_info")

@app.route('/system/disk/usage', methods=['GET'])
def get_disk_usage():
    """Return disk usage information."""
    return _execute_detailed_script("disk_usage")

@app.route('/system/disk/partitions', methods=['GET'])
def get_disk_partitions():
    """Return disk partitions information."""
    return _execute_detailed_script("disk_partitions")

@app.route('/system/disk/smart', methods=['GET'])
def get_smart_info():
    """Return S.M.A.R.T. disk information."""
    return _execute_detailed_script("smart_info")

@app.route('/system/network/interfaces', methods=['GET'])
def get_network_interfaces():
    """Return network interfaces information."""
    return _execute_detailed_script("network_interfaces")

@app.route('/system/network/routing', methods=['GET'])
def get_routing_table():
    """Return network routing table information."""
    return _execute_detailed_script("routing_table")

@app.route('/system/network/connections', methods=['GET'])
def get_connections():
    """Return TCP/UDP connections information."""
    return _execute_detailed_script("tcp_udp_connections")

@app.route('/system/network/firewall', methods=['GET'])
def get_firewall_rules():
    """Return firewall rules information."""
    return _execute_detailed_script("firewall_rules")

def _execute_detailed_script(module_name):
    """Helper function to execute get_detailed.sh with the specified module name."""
    try:
        # Map from function name to CLI parameter
        module_map = {
            "os_info": "os",
            "cpu_info": "cpu",
            "disk_usage": "disk_usage",
            "disk_partitions": "disk_parts",
            "smart_info": "smart",
            "network_interfaces": "network",
            "routing_table": "routing",
            "tcp_udp_connections": "connections",
            "firewall_rules": "firewall"
        }
        
        cli_param = module_map.get(module_name)
        if not cli_param:
            return jsonify({"error": f"Invalid module name: {module_name}"}), 400
            
        script_path = os.path.join(SCRIPT_DIR, "get_detailed.sh")
        stdout, stderr, code = run_command(["sudo", script_path, cli_param])
        
        if code != 0:
            return jsonify({"error": f"Failed to get {module_name}: {stderr}"}), 500
        
        try:
            # Parse the JSON output
            data = json.loads(stdout)
            return jsonify(data)
        except json.JSONDecodeError as e:
            return jsonify({
                "error": f"Failed to parse JSON output: {str(e)}",
                "raw_output": stdout
            }), 500
    except Exception as e:
        return jsonify({"error": f"Failed to execute {module_name} script: {str(e)}"}), 500

# New improved service information parsing methods

def _parse_systemctl_show_output(output):
    """Parse the output of systemctl show into a dictionary."""
    result = {}
    filter_values = ["n/a", "0", "infinity", "[no data]", "null", "[not set]", ""]
    
    for line in output.strip().split('\n'):
        if '=' in line:
            key, value = line.split('=', 1)
            # Skip filtered values
            if value in filter_values:
                continue
            result[key] = value
    
    return result

def _parse_exec_directive(directive_value):
    """Parse systemd Exec* directives into structured data."""
    result = {}
    
    # Remove the outer braces
    if directive_value.startswith('{') and directive_value.endswith('}'):
        directive_value = directive_value[1:-1].strip()
    
    # Split by semicolons and process each part
    parts = directive_value.split(';')
    for part in parts:
        part = part.strip()
        if not part:
            continue
            
        if '=' in part:
            key, value = part.split('=', 1)
            key = key.strip()
            value = value.strip()
            
            # Handle arrays
            if key.endswith('[]'):
                key = key.replace('[]', '')
                # Convert to array format
                if value:
                    result[key] = value.split()
                else:
                    result[key] = []
            else:
                result[key] = value
    
    return result

def _parse_environment_directive(directive_value):
    """Parse systemd Environment directive into structured data."""
    result = {}
    
    # Split environment variables (space-separated)
    env_vars = directive_value.split()
    
    for env_var in env_vars:
        if '=' in env_var:
            key, value = env_var.split('=', 1)
            
            # Handle comma-separated values as arrays
            if ',' in value:
                result[key] = value.split(',')
            else:
                result[key] = value
    
    return result

def _parse_x_metadata(service_name):
    """Parse X-Metadata fields from service configuration with nested structure."""
    metadata = {}
    
    # We need to use 'cat' to get X-Metadata fields
    stdout, stderr, code = run_command(["sudo", "systemctl", "cat", f"{service_name}.service"])
    if code != 0:
        return metadata
    
    # Find all X-Metadata fields
    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith('X-Metadata-'):
            # Remove prefix and parse key=value
            x_data = line[len('X-Metadata-'):]
            if '=' in x_data:
                key_path, value = x_data.split('=', 1)
                
                # Convert to lowercase for consistency
                key_path = key_path.lower()
                
                # Split by underscore to get the nested structure
                keys = key_path.split('_')
                
                # Build the nested structure
                current = metadata
                for i, k in enumerate(keys):
                    if i == len(keys) - 1:
                        # Last key, set the value
                        current[k] = value.replace('"', '').strip()
                    else:
                        # Create nested dict if needed
                        if k not in current:
                            current[k] = {}
                        current = current[k]
    
    return metadata

def get_service_details_v2(service_name):
    """Get detailed service status using systemctl show."""
    # Check if service exists
    loaded_check, _, _ = run_command(["sudo", "systemctl", "show", f"{service_name}.service", "--property=LoadState"])
    if "not-found" in loaded_check.lower():
        return {"error": f"Service {service_name} not found"}
    
    # Get service properties using systemctl show
    stdout, stderr, code = run_command(["sudo", "systemctl", "show", f"{service_name}.service"])
    if code != 0:
        return {"error": f"Failed to get service details: {stderr}"}
    
    # Parse the output
    service_data = _parse_systemctl_show_output(stdout)
    
    # Add simplified status fields for compatibility
    result = {
        "service": service_name,
        "running": service_data.get("ActiveState") == "active",
        "enabled": service_data.get("UnitFileState") in ["enabled", "indirect", "static"],
        "details": {}
    }
    
    # Process Exec* directives
    for key, value in list(service_data.items()):
        if key.startswith("Exec") and value.startswith("{"):
            service_data[key] = _parse_exec_directive(value)
    
    # Process Environment directive
    if "Environment" in service_data:
        service_data["Environment"] = _parse_environment_directive(service_data["Environment"])
    
    # Add the full data
    result["details"] = service_data
    
    # Add additional compatibility fields
    if "ActiveState" in service_data:
        result["active_raw"] = service_data.get("ActiveState")
    
    if "UnitFileState" in service_data:
        result["boot_status"] = service_data.get("UnitFileState")
    
    if "ActiveEnterTimestamp" in service_data:
        result["started_at"] = service_data.get("ActiveEnterTimestamp")
    
    if "MainPID" in service_data and service_data["MainPID"] != "0":
        result["details"]["pid"] = int(service_data["MainPID"])
    
    return result

def get_service_unit_info_v2(service_name):
    """Extract and return the configuration of a service with improved parsing."""
    # Check if service exists
    loaded_check, _, _ = run_command(["sudo", "systemctl", "show", f"{service_name}.service", "--property=LoadState"])
    if "not-found" in loaded_check.lower():
        return {"error": f"Service {service_name} not found"}
    
    # Get service properties using systemctl show
    stdout, stderr, code = run_command(["sudo", "systemctl", "show", f"{service_name}.service"])
    if code != 0:
        return {"error": f"Failed to get service details: {stderr}"}
    
    # Parse the output
    all_properties = _parse_systemctl_show_output(stdout)
    
    # Group properties into sections
    sections = {"Unit": {}, "Service": {}, "Install": {}}
    
    # Map known properties to sections
    section_prefixes = {
        "Unit": ["Description", "Documentation", "Before", "After", "Wants", "Requires"],
        "Service": ["Type", "ExecStart", "ExecStop", "Restart", "Environment", "User", "Group", "WorkingDirectory"],
        "Install": ["WantedBy", "Alias"]
    }
    
    # Assign properties to sections
    for key, value in all_properties.items():
        assigned = False
        for section, prefixes in section_prefixes.items():
            for prefix in prefixes:
                if key.startswith(prefix):
                    # Process Exec* directives
                    if key.startswith("Exec") and value.startswith("{"):
                        sections[section][key] = _parse_exec_directive(value)
                    # Process Environment directive
                    elif key == "Environment":
                        sections[section][key] = _parse_environment_directive(value)
                    else:
                        sections[section][key] = value
                    assigned = True
                    break
            if assigned:
                break
    
    # Get X-Metadata fields
    custom_metadata = _parse_x_metadata(service_name)
    
    return {
        "service": service_name,
        "config": sections,
        "metadata": custom_metadata,
        "all_properties": all_properties  # Include all properties for reference
    }

# Add new endpoint for testing the new methods
@app.route('/services/<service_name>/details', methods=['GET'])
def service_details_v2(service_name):
    """Return detailed service information using the improved parser."""
    if service_name not in services_config:
        abort(404, description="Service not found")
    details = get_service_details_v2(service_name)
    return jsonify(details)

@app.route('/services/<service_name>/unit_info', methods=['GET'])
def service_unit_info_v2(service_name):
    """Return service unit information using the improved parser."""
    if service_name not in services_config:
        abort(404, description="Service not found")
    info = get_service_unit_info_v2(service_name)
    return jsonify(info)

if __name__ == '__main__':
    # Run on all interfaces on port 5000.
    app.run(host='0.0.0.0', port=5000)
