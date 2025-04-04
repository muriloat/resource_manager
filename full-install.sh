#!/bin/bash
# Resource Manager Full Installation Script
# This script installs both the Resource Manager UI and Server components,
# discovers all local services, and lets users select which ones to manage.
# Author: Murilo Teixeira - dev@murilo.etc.br
# Refer to https://github.com/muriloat/resource_manager for more information.
# Usage: sudo ./full-install.sh

set -euo pipefail

# Ensure we run as root
if [[ $EUID -ne 0 ]]; then
  echo "This script must be run as root (try sudo)." >&2
  exit 1
fi

# Define a reusable function for service selection
select_services() {
  # Get all systemd services that are either active or enabled
  echo "Finding all systemd services..."
  local ALL_SERVICES=$(systemctl list-units --type=service --state=active,enabled --no-legend | awk '{print $1}' | sed 's/\.service$//')
  local ACTIVE_SERVICES=()

  # Create an associative array to map display names to actual service names
  declare -A SERVICE_MAP

  # Check which services are active and format them for display
  for SERVICE in ${ALL_SERVICES}; do
    # Determine the service status
    if systemctl is-active "${SERVICE}.service" >/dev/null 2>&1; then
      STATUS="Active "
    elif systemctl is-enabled "${SERVICE}.service" >/dev/null 2>&1; then
      STATUS="Enabled "
    else
      continue
    fi
    
    # Truncate very long service names to prevent display issues
    DISPLAY_NAME="${SERVICE}"
    if [ ${#DISPLAY_NAME} -gt 33 ]; then
      DISPLAY_NAME="${DISPLAY_NAME:0:33}..."
    fi
    DISPLAY_NAME=$(printf "%-25s" "${DISPLAY_NAME}") # pad to exactly 25 chars
    
    # Store mapping between display name and actual service name
    SERVICE_MAP["${DISPLAY_NAME}"]="${SERVICE}"
    
    # Add to the array with proper formatting
    ACTIVE_SERVICES+=("${DISPLAY_NAME}" "${STATUS}" "OFF")
  done

  # Display interactive menu to select services
  if [ ${#ACTIVE_SERVICES[@]} -eq 0 ]; then
    echo "No active or enabled services found."
    return 1
  fi

  echo "Displaying service selection menu..."
  # Use a taller and wider dialog to accommodate more services
  SELECTED_SERVICES=$(whiptail --title "Select Services to Manage" \
    --checklist "Choose services that Resource Manager should manage:" \
    25 57 17 "${ACTIVE_SERVICES[@]}" 3>&1 1>&2 2>&3)

  # Check if user cancelled
  if [ $? -ne 0 ]; then
    echo "User cancelled service selection. Exiting..."
    return 1
  fi

  # Remove quotes from whiptail output
  SELECTED_SERVICES=$(echo "${SELECTED_SERVICES}" | tr -d '"')

  # Convert string to array of display names
  read -ra DISPLAY_SERVICES <<< "${SELECTED_SERVICES}"

  # Convert display names back to actual service names
  local SELECTED=()
  for DISPLAY_NAME in "${DISPLAY_SERVICES[@]}"; do
    # Trim whitespace from display name before lookup
    TRIMMED_NAME=$(echo "${DISPLAY_NAME}" | xargs)
    
    # Loop through the keys in SERVICE_MAP to find a match
    SERVICE=""
    for KEY in "${!SERVICE_MAP[@]}"; do
      TRIMMED_KEY=$(echo "${KEY}" | xargs)
      if [[ "${TRIMMED_KEY}" == "${TRIMMED_NAME}" ]]; then
        SERVICE="${SERVICE_MAP[${KEY}]}"
        break
      fi
    done
    
    if [ -n "${SERVICE}" ]; then
      SELECTED+=("${SERVICE}")
    fi
  done

  if [ ${#SELECTED[@]} -eq 0 ]; then
    echo "No services selected."
    return 1
  fi

  echo "Selected services: ${SELECTED[*]}"
  
  # Return the selected services array
  SERVICES=("${SELECTED[@]}")
  return 0
}

# Vars
INSTALL_DIR=$(pwd)
BASE_DIR="${INSTALL_DIR}"
SERVER_INSTALL_DIR="${BASE_DIR}/server"
VENV_DIR="${BASE_DIR}/venv"
CONFIG_DIR="${BASE_DIR}/config"
LOGS_DIR="${BASE_DIR}/logs"
SERVICE_USER="resource_manager"
SYSTEMD_UI_FILE_NAME="resource_manager_ui.service"
SYSTEMD_UI_SERVICE_FILE="/etc/systemd/system/${SYSTEMD_UI_FILE_NAME}"
SYSTEMD_SERVER_FILE_NAME="resource_manager_server.service"
SYSTEMD_SERVER_SERVICE_FILE="/etc/systemd/system/${SYSTEMD_SERVER_FILE_NAME}"
SUDOERS_FILE="/etc/sudoers.d/resource_manager"

# Create necessary directories
mkdir -p "${CONFIG_DIR}" "${LOGS_DIR}" "${SERVER_INSTALL_DIR}"

echo "==== Resource Manager Full Installation ===="
echo "This script will install and configure both the Resource Manager UI and Server."
echo "Installation directory: ${INSTALL_DIR}"

# Check if server directory exists
if [ ! -f "${SERVER_INSTALL_DIR}/resource_manager_server.py" ]; then
  echo "Error: Server files not found in ${SERVER_INSTALL_DIR}." >&2
  echo "Please ensure the repository is properly cloned with all required files." >&2
  exit 1
fi

# Install dependencies
echo "Installing required packages..."
apt-get update -y && apt-get install -y python3-venv python3-pip python-is-python3 smartmontools whiptail

# Call the service selection function
select_services
if [ $? -ne 0 ]; then
  exit 1
fi

# 1. Setup Virtual Environment
echo "Setting up Python virtual environment..."
python3 -m venv "${VENV_DIR}"
source "${VENV_DIR}/bin/activate"
pip install --upgrade pip
pip install flask flask-cors flask-socketio requests
deactivate

# 2. Create user if not exists
if ! id -u ${SERVICE_USER} >/dev/null 2>&1; then
  echo "Creating system user ${SERVICE_USER}..."
  adduser --system --no-create-home --group ${SERVICE_USER}
else
  echo "User ${SERVICE_USER} already exists."
fi

# 3. Generate services_config.py for server
echo "Generating services_config.py..."
SERVICES_CONFIG_FILE="${SERVER_INSTALL_DIR}/services_config.py"
cat <<EOF > "${SERVICES_CONFIG_FILE}"
# Auto-generated services configuration file.
# Each service is defined with default timeouts (10 seconds) and a placeholder for start_string you must edit.
# Adjust the timeout values as needed for your services.
# The start_string should be a unique string that appears in the logs when the service has successfully started.
# You can find this string by restarting your service and checking the logs with 'journalctl -u <service_name>.service -f'.
# After editing the start_string, restart the resource_manager service to apply the changes.
services_config = {
EOF

# Validate services exist and find their locations
VALID_SERVICES=()
SERVICE_LOCATIONS=()

for SERVICE in "${SERVICES[@]}"; do
  # Check common locations for systemd service files
  if [ -f "/etc/systemd/system/${SERVICE}.service" ]; then
    echo "Found service ${SERVICE} in /etc/systemd/system/"
    VALID_SERVICES+=("${SERVICE}")
    SERVICE_LOCATIONS+=("/etc/systemd/system/${SERVICE}.service")
  elif [ -f "/lib/systemd/system/${SERVICE}.service" ]; then
    echo "Found service ${SERVICE} in /lib/systemd/system/"
    VALID_SERVICES+=("${SERVICE}")
    SERVICE_LOCATIONS+=("/lib/systemd/system/${SERVICE}.service")
  else
    echo "Warning: Service ${SERVICE} not found in common systemd directories. Adding anyway but verify it exists."
    VALID_SERVICES+=("${SERVICE}")
    SERVICE_LOCATIONS+=("unknown")
  fi

  cat <<EOF >> "${SERVICES_CONFIG_FILE}"
    "${SERVICE}": {"service_name": "${SERVICE}", "start_string": "Started ${SERVICE}.service -", "start_timeout": 10, "stop_timeout": 10},
EOF
done

echo "}" >> "${SERVICES_CONFIG_FILE}"
echo "" >> "${SERVICES_CONFIG_FILE}"
echo "# Files to never update" >> "${SERVICES_CONFIG_FILE}"
echo "preserved_files = [" >> "${SERVICES_CONFIG_FILE}"
echo "    \"server-bootstrap.sh\"," >> "${SERVICES_CONFIG_FILE}"  
echo "    \"server-uninstall.sh\"," >> "${SERVICES_CONFIG_FILE}"
echo "]" >> "${SERVICES_CONFIG_FILE}"

# 4. Setup environment file for proper paths
cat <<EOF > "${BASE_DIR}/.env"
RESOURCE_MANAGER_LOG_FILE="logs/rm.log"
RESOURCE_MANAGER_LOG_LEVEL="DEBUG"
RESOURCE_MANAGER_CONFIG_DIR="config"
EOF

# 5. Create sudoers file for the service user
echo "Creating sudoers file at ${SUDOERS_FILE}..."
SYSTEMCTL_PATH=$(which systemctl)
JOURNALCTL_PATH=$(which journalctl)

{
  echo "${SERVICE_USER} ALL=(root) NOPASSWD: \\"
  for SERVICE in "${VALID_SERVICES[@]}"; do
    echo "  ${SYSTEMCTL_PATH} start ${SERVICE}.service, \\"
    echo "  ${SYSTEMCTL_PATH} stop ${SERVICE}.service, \\"
    echo "  ${SYSTEMCTL_PATH} status ${SERVICE}.service, \\"
    echo "  ${SYSTEMCTL_PATH} enable ${SERVICE}.service, \\"
    echo "  ${SYSTEMCTL_PATH} disable ${SERVICE}.service, \\"
    echo "  ${SYSTEMCTL_PATH} is-active ${SERVICE}.service, \\"
    echo "  ${SYSTEMCTL_PATH} is-enabled ${SERVICE}.service, \\"
    echo "  ${SYSTEMCTL_PATH} --version, \\"
    echo "  ${SYSTEMCTL_PATH} cat ${SERVICE}.service, \\"
    echo "  ${SYSTEMCTL_PATH} show ${SERVICE}.service --property=LoadState, \\"
    echo "  ${JOURNALCTL_PATH} -u ${SERVICE}.service * -n *, \\"
    echo "  ${JOURNALCTL_PATH} -u ${SERVICE}.service -f, \\"
    echo "  ${JOURNALCTL_PATH} -u ${SERVICE}.service -n * --since * --no-pager, \\"
    echo "  ${JOURNALCTL_PATH} -u ${SERVICE}.service --since * --no-pager, \\"
  done
  
  # Add permissions for get_detailed.sh script and common system tools
  echo "  ${SERVER_INSTALL_DIR}/get_detailed.sh *, \\"
  echo "  /usr/sbin/smartctl * *, \\"
  echo "  /usr/sbin/fdisk * *, \\"
  echo "  /usr/bin/lsblk * *, \\"
  echo "  /usr/bin/netstat * *, \\"
  echo "  /usr/sbin/route * *, \\"
  echo "  /usr/sbin/iptables * *"
} > "${SUDOERS_FILE}"

# Remove the trailing comma and backslash from the last line to ensure valid sudoers syntax
sed -i '$ s/,\s*\\\s*$//' "${SUDOERS_FILE}"
chmod 440 "${SUDOERS_FILE}"

# 6. Create the UI systemd service file
echo "Creating UI systemd service file at ${SYSTEMD_UI_SERVICE_FILE}..."
cat <<EOF > "${SYSTEMD_UI_SERVICE_FILE}"
[Unit]
Description=Resource Manager Client UI
After=network.target

[Service]
Type=simple
User=${SERVICE_USER}
Group=${SERVICE_USER}
WorkingDirectory=${BASE_DIR}
ExecStart=${VENV_DIR}/bin/python -m resource_manager.client.ui.app
Environment="PORT=8081"
Environment="HOST=0.0.0.0"
Environment="DEBUG=ERROR"
Environment="COMPUTERNAME=$(hostname)" 
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

# 7. Create the Server systemd service file
echo "Creating Server systemd service file at ${SYSTEMD_SERVER_SERVICE_FILE}..."
cat <<EOF > "${SYSTEMD_SERVER_SERVICE_FILE}"
[Unit]
Description=Resource Manager Server - API Service
After=network.target

[Service]
Type=simple
User=${SERVICE_USER}
Group=${SERVICE_USER}
WorkingDirectory=${SERVER_INSTALL_DIR}
ExecStart=${VENV_DIR}/bin/python ${SERVER_INSTALL_DIR}/resource_manager_server.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

# 8. Set proper file ownership
echo "Setting ownership for ${SERVICE_USER}..."
chown -R ${SERVICE_USER}:${SERVICE_USER} "${BASE_DIR}"
chmod +x "${SERVER_INSTALL_DIR}/get_detailed.sh" 2>/dev/null || true

# 9. Reload systemd, enable and start the services
echo "Reloading systemd daemon..."
systemctl daemon-reload

echo "Enabling and starting ${SYSTEMD_SERVER_FILE_NAME}..."
systemctl enable ${SYSTEMD_SERVER_FILE_NAME}
systemctl start ${SYSTEMD_SERVER_FILE_NAME}

echo "Enabling and starting ${SYSTEMD_UI_FILE_NAME}..."
systemctl enable ${SYSTEMD_UI_FILE_NAME}
systemctl start ${SYSTEMD_UI_FILE_NAME}

# 10. Print summary of service locations
echo "==== Installation Summary ===="
echo ""
echo "Service locations:"
for i in "${!VALID_SERVICES[@]}"; do
  echo "  - ${VALID_SERVICES[$i]}: ${SERVICE_LOCATIONS[$i]}"
done
echo ""
echo " - Resource Manager UI service: ${SYSTEMD_UI_SERVICE_FILE}"
echo " - Resource Manager Server service: ${SYSTEMD_SERVER_SERVICE_FILE}"
echo " - Sudoers file: ${SUDOERS_FILE}"
echo " - Config directory: ${CONFIG_DIR}"
echo " - Logs directory: ${LOGS_DIR}"
echo ""
echo "Installation complete!"
echo "To access the UI, open your web browser and go to http://$(hostname -I | awk '{print $1}'):8081"

