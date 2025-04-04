# Description: This script uninstalls the Resource Manager server from the system.
# Usage: sudo ./server-uninstall.sh 

#!/bin/bash
set -euo pipefail

# This script must be run as root.
if [[ $EUID -ne 0 ]]; then
  echo "This script must be run as root. Try running with sudo."
  exit 1
fi

echo "Uninstalling Resource Manager server..."

# Define variables
SERVICE_NAME="resource_manager_server.service"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}"
SUDOERS_FILE="/etc/sudoers.d/resource_manager"
BASE_DIR="opt/resource_manager"
INSTALL_DIR="${BASE_DIR}/server"
SERVICE_USER="resource_manager"

# Stop the service if it's running
if systemctl is-active --quiet ${SERVICE_NAME}; then
  echo "Stopping ${SERVICE_NAME}..."
  systemctl stop ${SERVICE_NAME}
fi

# Disable the service if enabled
if systemctl is-enabled --quiet ${SERVICE_NAME}; then
  echo "Disabling ${SERVICE_NAME}..."
  systemctl disable ${SERVICE_NAME}
fi

# Remove the systemd service file
if [[ -f "${SERVICE_FILE}" ]]; then
  echo "Removing systemd service file: ${SERVICE_FILE}"
  rm -f "${SERVICE_FILE}"
  systemctl daemon-reload
fi

# Remove the sudoers file
if [[ -f "${SUDOERS_FILE}" ]]; then
  echo "Removing sudoers file: ${SUDOERS_FILE}"
  rm -f "${SUDOERS_FILE}"
fi

# Remove the installation directory
if [[ -d "${INSTALL_DIR}" ]]; then
  echo "Removing installation directory: ${INSTALL_DIR}"
  rm -rf "${INSTALL_DIR}"
fi

# Delete the dedicated system user (and its group if appropriate)
if id "${SERVICE_USER}" &>/dev/null; then
  echo "Deleting system user: ${SERVICE_USER}"
  # On Debian/Ubuntu, deluser is usually available:
  if command -v deluser &>/dev/null; then
    deluser --remove-home "${SERVICE_USER}" || true
  else
    userdel "${SERVICE_USER}" || true
  fi
fi

echo "Resource Manager server has been successfully uninstalled. I value people's time, if this is no longer useful we will clean everything up before leaving."
