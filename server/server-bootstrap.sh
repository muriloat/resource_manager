#!/bin/bash
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
CONFIG_FILE="${INSTALL_DIR}/services_config.py"

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
  
  # Copy the install script from the repo to the installation directory
  cp "${TMP_DIR}/server/server-install.sh" "${INSTALL_DIR}/"
  chmod +x "${INSTALL_DIR}/server-install.sh"
  
  # Run the installation script with the provided services
  "${INSTALL_DIR}/server-install.sh" "$@"
else
  # No arguments provided
  # Check if this is a fresh installation (no existing config)
  if [[ ! -f "${CONFIG_FILE}" ]]; then
    echo "WARNING: No services specified for installation!"
    echo "-----------------------------------------------"
    echo "This appears to be a fresh installation, but no services were specified."
    echo "Without specifying services to manage, the Resource Manager will be installed"
    echo "but won't be configured to manage any services."
    echo ""
    echo "Recommended usage: sudo server-bootstrap.sh service1 service2 ..."
    echo "Example: sudo server-bootstrap.sh nginx mysql docker"
    echo "or"
    echo "Recommended usage: curl -sSL https://raw.githubusercontent.com/muriloat/resource_manager/refs/heads/main/server/server-bootstrap.sh | sudo bash -s service1 service2 ..."
    echo "Example: curl -sSL https://raw.githubusercontent.com/muriloat/resource_manager/refs/heads/main/server/server-bootstrap.sh | sudo bash -s nginx mysql docker"
    
    # Ask for confirmation
    read -p "Do you want to continue anyway? (y/N): " -n 1 -r CONFIRM
    echo ""
    
    if [[ ! $CONFIRM =~ ^[Yy]$ ]]; then
      echo "Installation aborted. Please run again with service names."
      rm -rf "${TMP_DIR}"
      exit 1
    fi
    
    echo "Proceeding with installation without service specifications..."
  fi
  
  # Update mode - no arguments
  echo "Bootstrapping Resource Manager update..."
  
  # Copy the update script from the repo to the installation directory
  cp "${TMP_DIR}/server/server-update.sh" "${INSTALL_DIR}/"
  chmod +x "${INSTALL_DIR}/server-update.sh"
  
  # Run the update script from the repository
  "${INSTALL_DIR}/server-update.sh" --repo-path="${TMP_DIR}"
fi

# Clean up
rm -rf "${TMP_DIR}"

echo "Resource Manager operation completed successfully."
exit 0
