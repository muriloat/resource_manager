#!/bin/bash
# This script installs the Resource Manager server and sets up the provided services.
# It creates a system user for the server, a Python virtual environment, a systemd service,
# and a sudoers file for the system user to manage the services.
# Author: Murilo Teixeira - dev@murilo.etc.br
# Refer to https://github.com/muriloat/resource_manager for more information.
# Usage: sudo ./server-install.sh

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
REPO_URL="https://github.com/muriloat/resource_manager.git"
TMP_DIR=$(mktemp -d)
BASE_DIR="/opt/resource_manager"
INSTALL_DIR="${BASE_DIR}/server"
VENV_DIR="${BASE_DIR}/venv"
SERVICE_USER="resource_manager"
SUDOERS_FILE="/etc/sudoers.d/resource_manager"
SYSTEMD_FILE_NAME="resource_manager_server.service"
SYSTEMD_SERVICE_FILE="/etc/systemd/system/${SYSTEMD_FILE_NAME}"

# Packages dependencies:
echo "Installing Dependencies..."
apt-get update -y && apt-get install python3-venv python3-pip python-is-python3 smartmontools whiptail -y

# Call the service selection function
select_services
if [ $? -ne 0 ]; then
  exit 1
fi

# Clone the repository
echo "Cloning repository from ${REPO_URL}..."
git clone --depth 1 "${REPO_URL}" "${TMP_DIR}" || { echo "Git clone failed"; exit 1; }

# Create the installation directory
echo "Creating installation directory at ${INSTALL_DIR}..."
mkdir -p "${INSTALL_DIR}"

# Copy server files from the repo
echo "Copying server files..."
cp "${TMP_DIR}/server/server-uninstall.sh" "${INSTALL_DIR}/"
cp "${TMP_DIR}/server/resource_manager_server.py" "${INSTALL_DIR}/"
cp "${TMP_DIR}/server/requirements.txt" "${INSTALL_DIR}/"
cp "${TMP_DIR}/server/server-bootstrap.sh" "${INSTALL_DIR}/"
cp "${TMP_DIR}/server/server-update.sh" "${INSTALL_DIR}/"
cp "${TMP_DIR}/server/get_detailed.sh" "${INSTALL_DIR}/"
cp "${TMP_DIR}/server/fixed_pagination.py" "${INSTALL_DIR}/"
chmod +x "${INSTALL_DIR}/server-bootstrap.sh"
chmod +x "${INSTALL_DIR}/server-uninstall.sh"
chmod +x "${INSTALL_DIR}/server-update.sh"
chmod +x "${INSTALL_DIR}/get_detailed.sh"

# Create services_config.py from the selected services
echo "Generating services_config.py..."
SERVICES_CONFIG_FILE="${INSTALL_DIR}/services_config.py"
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

# Set up the Python virtual environment and install dependencies
echo "Setting up Python virtual environment in ${VENV_DIR}..."
python3 -m venv "${VENV_DIR}"
source "${VENV_DIR}/bin/activate"
pip install --upgrade pip
pip install -r "${INSTALL_DIR}/requirements.txt"
deactivate

# Create dedicated system user
if ! id -u ${SERVICE_USER} >/dev/null 2>&1; then
  echo "Creating system user ${SERVICE_USER}..."
  adduser --system --no-create-home --group ${SERVICE_USER}
else
  echo "User ${SERVICE_USER} already exists."
fi

# Set ownership of the installation directory
echo "Setting ownership of ${INSTALL_DIR} to ${SERVICE_USER}..."
chown -R ${SERVICE_USER}:${SERVICE_USER} "${INSTALL_DIR}"

# Capture full paths for systemctl and journalctl
SYSTEMCTL_PATH=$(which systemctl)
JOURNALCTL_PATH=$(which journalctl)
echo "Found systemctl at: ${SYSTEMCTL_PATH}"
echo "Found journalctl at: ${JOURNALCTL_PATH}"

# Create sudoers file for the service user
echo "Creating sudoers file at ${SUDOERS_FILE}..."
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
  
  # Add permissions for get_detailed.sh script
  echo "  ${INSTALL_DIR}/get_detailed.sh *, \\"
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

# Create the systemd service file
echo "Creating systemd service file at ${SYSTEMD_SERVICE_FILE}..."
cat <<EOF > "${SYSTEMD_SERVICE_FILE}"
[Unit]
Description=Resource Manager Server - API Service
After=network.target

[Service]
Type=simple
User=${SERVICE_USER}
Group=${SERVICE_USER}
WorkingDirectory=${INSTALL_DIR}
ExecStart=${VENV_DIR}/bin/python ${INSTALL_DIR}/resource_manager_server.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd, enable and start the service
echo "Reloading systemd daemon..."
systemctl daemon-reload
echo "Enabling ${SYSTEMD_FILE_NAME}..."
systemctl enable ${SYSTEMD_FILE_NAME}
echo "Starting ${SYSTEMD_FILE_NAME}..."
systemctl start ${SYSTEMD_FILE_NAME}

# Clean up temporary files
rm -rf "${TMP_DIR}"
# We don't need install script anymore
rm -f "${INSTALL_DIR}/server-install.sh"

# Print summary of service locations
echo "Service locations summary:"
for i in "${!VALID_SERVICES[@]}"; do
  echo "  ${VALID_SERVICES[$i]}: ${SERVICE_LOCATIONS[$i]}"
done

echo "Installation complete!"
