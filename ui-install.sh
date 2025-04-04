#!/bin/bash
# This script installs the Resource Manager Client UI and sets up as service.
# It creates a system user for the client, a Python virtual environment and a systemd service,
# Author: Murilo Teixeira - dev@murilo.etc.br
# Refer to https://github.com/muriloat/resource_manager for more information.
# Usage: sudo ./ui-install.sh

set -euo pipefail

# Ensure we run as root
if [[ $EUID -ne 0 ]]; then
  echo "This script must be run as root (try sudo)." >&2
  exit 1
fi

# Check for parameters
# FIXED: Changed condition to match usage
if [ "$#" -gt 0 ]; then
  echo "Usage: $0" >&2
  exit 1
fi

# Packages dependencies:
echo "Installing Dependencies..."
apt-get update -y && apt-get install python3-venv python3-pip python-is-python3 smartmontools -y


# Vars
INSTALL_DIR=$(pwd)
VENV_DIR=$(pwd)/venv
SERVICE_USER="resource_manager"
SYSTEMD_FILE_NAME="resource_manager_ui.service"
SYSTEMD_SERVICE_FILE="/etc/systemd/system/${SYSTEMD_FILE_NAME}"

echo "Installing Resource Manager UI service: $*"

# Set up the Python virtual environment and install dependencies
echo "Setting up Python virtual environment..."
python3 -m venv "${VENV_DIR}"
source "${VENV_DIR}/bin/activate"
pip install --upgrade pip
pip install flask flask-cors flask-socketio requests
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

# Create the systemd service file
echo "Creating systemd service file at ${SYSTEMD_SERVICE_FILE}..."
cat <<EOF > "${SYSTEMD_SERVICE_FILE}"
[Unit]
Description=Resource Manager Client UI
After=network.target

[Service]
Type=simple
User=${SERVICE_USER}
Group=${SERVICE_USER}
WorkingDirectory=${INSTALL_DIR}
ExecStart=${VENV_DIR}/bin/python -m resource_manager.client.ui.app
Environment="PORT=8081"
Environment="HOST=0.0.0.0"
Environment="DEBUG=ERROR"
Environment="COMPUTERNAME=$(hostname)" 
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

# Local Resource Manager Server Installation






# Check the status of the service
echo "Checking the status of ${SYSTEMD_FILE_NAME}..."
systemctl status ${SYSTEMD_FILE_NAME} --no-pager
if [ $? -ne 0 ]; then
  echo "Failed to start ${SYSTEMD_FILE_NAME}. Check the logs for more details." >&2
  exit 1
fi
echo "Service ${SYSTEMD_FILE_NAME} started successfully."
echo "To access the UI, open your web browser and go to http://<your-server-ip>:8081"
echo "To stop the service, use: sudo systemctl stop ${SYSTEMD_FILE_NAME}"
echo "To start the service, use: sudo systemctl start ${SYSTEMD_FILE_NAME}"
echo "To check the logs, use: journalctl -u ${SYSTEMD_FILE_NAME} -f"

echo "Installation complete!"
