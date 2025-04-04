#!/bin/bash
# Script to bootstrap the Resource Manager Server

set -euo pipefail

# This script must be run as root
if [[ $EUID -ne 0 ]]; then
  echo "This script must be run as root. Try running with sudo."
  exit 1
fi

# Define variables
REPO_URL="https://github.com/muriloat/resource_manager.git"
BASE_DIR="/opt/resource_manager"
INSTALL_DIR="${BASE_DIR}/server"
VENV_DIR="${BASE_DIR}/venv"
TMP_DIR=$(mktemp -d)
OPERATION="operation"

# Clone the latest version of the repository
echo "Downloading latest code from ${REPO_URL}..."
git clone --depth 1 "${REPO_URL}" "${TMP_DIR}" || { 
  echo "Git clone failed" 
  rm -rf "${TMP_DIR}"
  exit 1
}

# Check if this is an installation or update
if [[ ! -d "${INSTALL_DIR}" || ! -f "${INSTALL_DIR}/resource_manager_server.py" ]]; then
  # Installation mode - server doesn't exist yet
  echo "No existing installation found. Running Resource Manager installation..."
  OPERATION="install"
  
  # Create installation directory if it doesn't exist
  mkdir -p "${INSTALL_DIR}"
  
  # Copy the install script from the repo to the installation directory
  cp "${TMP_DIR}/server/server-install.sh" "${INSTALL_DIR}/"
  chmod +x "${INSTALL_DIR}/server-install.sh"
  
  # Install required packages for the interactive menu
  apt-get update -y && apt-get install -y whiptail
  
  echo "===================================================================="
  echo "IMPORTANT: Running service selection menu. If you're installing via"
  echo "curl pipe to bash, the menu may not work correctly."
  echo ""
  echo "If you encounter any issues with the menu, press Ctrl+C to cancel,"
  echo "then run the installer directly with:"
  echo "  sudo ${INSTALL_DIR}/server-install.sh"
  echo "===================================================================="
  sleep 3
  
  # Run the installation script
  "${INSTALL_DIR}/server-install.sh"
else
  # Update mode - server already exists
  echo "Existing installation found. Bootstrapping Resource Manager update..."
  OPERATION="update"
  
  # Copy the update script from the repo to the installation directory
  cp "${TMP_DIR}/server/server-update.sh" "${INSTALL_DIR}/"
  chmod +x "${INSTALL_DIR}/server-update.sh"
  
  # Run the update script from the repository
  "${INSTALL_DIR}/server-update.sh" --repo-path="${TMP_DIR}"
fi

# Clean up
rm -rf "${TMP_DIR}"

echo "Resource Manager Server ${OPERATION} completed successfully."
exit 0
