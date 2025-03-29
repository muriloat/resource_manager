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
INSTALL_DIR="/opt/resource_manager"
TMP_DIR=$(mktemp -d)
OPERATION="operation"

# Create installation directory if it doesn't exist
mkdir -p "${INSTALL_DIR}"

# Clone the latest version of the repository
echo "Downloading latest code from ${REPO_URL}..."
git clone --depth 1 "${REPO_URL}" "${TMP_DIR}" || { 
  echo "Git clone failed" 
  rm -rf "${TMP_DIR}"
  exit 1
}

# Check if this is an installation or update
if [[ $# -gt 0 ]]; then
  # Installation mode with service arguments
  echo "Running Resource Manager installation for services: $*"
  OPERATION="install"
  # Copy the install script from the repo to the installation directory
  cp "${TMP_DIR}/server/server-install.sh" "${INSTALL_DIR}/"
  chmod +x "${INSTALL_DIR}/server-install.sh"
  
  # Run the installation script with the provided services
  "${INSTALL_DIR}/server-install.sh" "$@"
else
  # Update mode - no arguments
  echo "Bootstrapping Resource Manager update..."
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
