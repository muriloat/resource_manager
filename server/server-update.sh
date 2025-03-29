# Description: This script updates the Resource Manager server from github.
# Usage: sudo ./server-update.sh 

#!/bin/bash
set -euo pipefail

# This script must be run as root.
if [[ $EUID -ne 0 ]]; then
  echo "This script must be run as root. Try running with sudo."
  exit 1
fi

# Parse command line arguments
REPO_PATH=""
while [[ $# -gt 0 ]]; do
  case $1 in
    --repo-path=*)
      REPO_PATH="${1#*=}"
      shift
      ;;
    *)
      echo "Unknown parameter: $1"
      exit 1
      ;;
  esac
done

echo "Updating Resource Manager server..."

# Define variables
SERVICE_NAME="resource_manager_manager.service"
SUDOERS_FILE="/etc/sudoers.d/resource_manager"
REPO_URL="https://github.com/muriloat/resource_manager.git"
INSTALL_DIR="/opt/resource_manager"
VENV_DIR="${INSTALL_DIR}/venv"
CONFIG_FILE="${INSTALL_DIR}/services_config.py"


# Extract preserved files from services_config.py if it exists
PRESERVED_FILES=("services_config.py" "server-bootstrap.sh")
if [[ -f "${CONFIG_FILE}" ]]; then
  echo "Reading configuration from ${CONFIG_FILE}..."
  # Extract preserved_files if defined in config
  if grep -q "preserved_files" "${CONFIG_FILE}"; then
    # Parse the Python list into a Bash array
    EXTRA_PRESERVED=$(grep "preserved_files" "${CONFIG_FILE}" | sed -E 's/.*\[([^]]*)\].*/\1/' | tr -d "' " | tr ',' ' ')
    PRESERVED_FILES+=(${EXTRA_PRESERVED})
  fi
  echo "Files to preserve during update: ${PRESERVED_FILES[*]}"
fi


# Service file

# Stop the service if it's running
if systemctl is-active --quiet ${SERVICE_NAME}; then
  echo "Stopping ${SERVICE_NAME}..."
  systemctl stop ${SERVICE_NAME}
fi

# Remove the sudoers file (create it again later)
if [[ -f "${SUDOERS_FILE}" ]]; then
  echo "Removing sudoers file: ${SUDOERS_FILE}"
  rm -f "${SUDOERS_FILE}"
fi

# Remove all files except preserved files
if [[ -d "${INSTALL_DIR}" ]]; then
  echo "Removing all files in installation directory except preserved files..."
  FIND_ARGS=("${INSTALL_DIR}" -type f)
  for file in "${PRESERVED_FILES[@]}"; do
    FIND_ARGS+=(! -name "${file}")
  done
  find "${FIND_ARGS[@]}" -delete
fi

# Use provided repo path or clone a new one
if [[ -z "${REPO_PATH}" ]]; then
  # Create a temporary directory and clone the repository
  TMP_DIR=$(mktemp -d)
  echo "Cloning repository from ${REPO_URL}..."
  git clone --depth 1 "${REPO_URL}" "${TMP_DIR}" || { 
    echo "Git clone failed" 
    rm -rf "${TMP_DIR}"
    exit 1
  }
  REPO_PATH="${TMP_DIR}"
  CLEANUP_REPO=true
else
  echo "Using provided repository path: ${REPO_PATH}"
  CLEANUP_REPO=false
fi

# Copy server files from the repo
echo "Copying server files..."
cp "${REPO_PATH}/server/resource_manager_server.py" "${INSTALL_DIR}/"
cp "${REPO_PATH}/server/requirements.txt" "${INSTALL_DIR}/"
cp "${REPO_PATH}/server/fixed_pagination.py" "${INSTALL_DIR}/"
cp "${REPO_PATH}/server/get_detailed.sh" "${INSTALL_DIR}/"
cp "${REPO_PATH}/server/server-update.sh" "${INSTALL_DIR}/"
chmod +x "${INSTALL_DIR}/server-update.sh"

# Merge service configurations if needed
if [[ -f "${CONFIG_FILE}" && -f "${REPO_PATH}/server/services_config.py" ]]; then
  echo "Merging service configurations..."
  
  # Create a temporary file for the merged configuration
  MERGED_CONFIG=$(mktemp)
  
  # Extract existing services from the current config file
  EXISTING_SERVICES=$(grep -A 1000 "services_config = {" "${CONFIG_FILE}" | 
                     grep -B 1000 -m 1 "^\}" | 
                     grep -v "services_config = {" | 
                     grep -v "^\}")
  
  # Extract new services from the repo config file
  NEW_SERVICES=$(grep -A 1000 "services_config = {" "${REPO_PATH}/server/services_config.py" | 
                grep -B 1000 -m 1 "^\}" | 
                grep -v "services_config = {" | 
                grep -v "^\}")
  
  # Create the new merged config file
  echo "# Resource Manager Service Configuration - Updated $(date)" > "${MERGED_CONFIG}"
  echo "" >> "${MERGED_CONFIG}"
  echo "# Service-specific configuration" >> "${MERGED_CONFIG}"
  echo "services_config = {" >> "${MERGED_CONFIG}"
  
  # Add existing services, removing duplicates that will be added from new services
  echo "${EXISTING_SERVICES}" | grep -v "^#" >> "${MERGED_CONFIG}"
  
  # Add new services, ensuring we don't add duplicate entries
  while IFS= read -r line; do
    # Skip comments and empty lines
    if [[ "${line}" == \#* || -z "${line}" ]]; then
      continue
    fi
    
    # Extract service name if this is a service entry
    if [[ "${line}" =~ \"([^\"]+)\" ]]; then
      X_SERVICE_NAME="${BASH_REMATCH[1]}"
      # Only add if service doesn't already exist in config
      if ! grep -q "\"${X_SERVICE_NAME}\":" "${MERGED_CONFIG}"; then
        echo "${line}" >> "${MERGED_CONFIG}"
      fi
    fi
  done <<< "${NEW_SERVICES}"
  
  echo "}" >> "${MERGED_CONFIG}"
  
  # Copy preserved_files section from current config if it exists
  if grep -q "preserved_files" "${CONFIG_FILE}"; then
    grep -A 100 "preserved_files" "${CONFIG_FILE}" | 
    grep -B 100 -m 1 "^\]" | 
    grep -v "sudo_permissions" >> "${MERGED_CONFIG}"
  else
    # Add default preserved_files section
    echo -e "\n# Files to preserve during update (in addition to services_config.py)" >> "${MERGED_CONFIG}"
    echo "preserved_files = [" >> "${MERGED_CONFIG}"
    echo "    \"server-bootstrap.sh\",  # The bootstrap script is now the main entry point" >> "${MERGED_CONFIG}"
    echo "    \"uninstall-server.sh\"," >> "${MERGED_CONFIG}"
    echo "]" >> "${MERGED_CONFIG}"
  fi
  
  # Move the merged config to replace the current one
  mv "${MERGED_CONFIG}" "${CONFIG_FILE}"
else
  # If no existing config, just copy the new one
  cp "${REPO_PATH}/server/services_config.py" "${INSTALL_DIR}/"
fi

# Extract valid services from the merged configuration
echo "Extracting service list from configuration..."
VALID_SERVICES=()
if [[ -f "${CONFIG_FILE}" ]]; then
  # Parse services from the config file
  while IFS= read -r line; do
    if [[ "${line}" =~ \"([^\"]+)\" ]]; then
      X_SERVICE_NAME="${BASH_REMATCH[1]}"
      VALID_SERVICES+=("${X_SERVICE_NAME}")
    fi
  done < <(grep -A 1000 "services_config = {" "${CONFIG_FILE}" | 
           grep -B 1000 -m 1 "^\}" | 
           grep -v "services_config = {" | 
           grep -v "^\}" | 
           grep -v "^#" | 
           grep "\".*\":")
fi

echo "Found ${#VALID_SERVICES[@]} services to manage: ${VALID_SERVICES[*]}"

# Clean up repository directory if we created it
if [[ "${CLEANUP_REPO}" == "true" ]]; then
  rm -rf "${REPO_PATH}"
fi

# Create the service user if it doesn't exist
SERVICE_USER="resource_manager"
if ! id -u "${SERVICE_USER}" >/dev/null 2>&1; then
  echo "Creating system user ${SERVICE_USER}..."
  adduser --system --no-create-home --group "${SERVICE_USER}"
else
  echo "Using existing user ${SERVICE_USER}"
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
  
  # Standard service permissions for each service
  for SERVICE in "${VALID_SERVICES[@]}"; do
    echo "  ${SYSTEMCTL_PATH} start ${SERVICE}.service, \\"
    echo "  ${SYSTEMCTL_PATH} stop ${SERVICE}.service, \\"
    echo "  ${SYSTEMCTL_PATH} status ${SERVICE}.service, \\"
    echo "  ${SYSTEMCTL_PATH} enable ${SERVICE}.service, \\"
    echo "  ${SYSTEMCTL_PATH} disable ${SERVICE}.service, \\"
    echo "  ${SYSTEMCTL_PATH} is-active ${SERVICE}.service, \\"
    echo "  ${SYSTEMCTL_PATH} is-enabled ${SERVICE}.service, \\"
    echo "  ${SYSTEMCTL_PATH} cat ${SERVICE}.service, \\"
    echo "  ${SYSTEMCTL_PATH} show ${SERVICE}.service --property=LoadState, \\"
    echo "  ${JOURNALCTL_PATH} -u ${SERVICE}.service * -n *, \\"
    echo "  ${JOURNALCTL_PATH} -u ${SERVICE}.service -f, \\"
    echo "  ${JOURNALCTL_PATH} -u ${SERVICE}.service -n * --since * --no-pager, \\"
    echo "  ${JOURNALCTL_PATH} -u ${SERVICE}.service --since * --no-pager, \\"
  done
  
  # Add global permissions
  echo "  ${SYSTEMCTL_PATH} --version, \\"
  
  # Add permissions for get_detailed.sh script
  echo "  ${INSTALL_DIR}/get_detailed.sh *, \\"
  echo "  /usr/sbin/smartctl * *, \\"
  echo "  /usr/sbin/fdisk * *, \\"
  echo "  /usr/bin/lsblk * *, \\"
  echo "  /usr/bin/netstat * *, \\"
  echo "  /usr/sbin/route * *, \\"
  echo "  /usr/sbin/iptables * *"
} > "${SUDOERS_FILE}"

chmod 440 "${SUDOERS_FILE}"

# Check if we need to update the systemd service file
SYSTEMD_SERVICE_FILE="/etc/systemd/system/resource_manager_server.service"
UPDATE_SERVICE_FILE=true

# Check if we're going to change the service file name
if [[ -f "${CONFIG_FILE}" ]] && grep -q "service_file_name" "${CONFIG_FILE}"; then
  # Extract the custom service file name
  CUSTOM_SERVICE_NAME=$(grep "service_file_name" "${CONFIG_FILE}" | sed -E 's/.*=\s*"([^"]+)".*/\1/')
  
  if [[ ! -z "${CUSTOM_SERVICE_NAME}" ]] && [[ "${CUSTOM_SERVICE_NAME}" != "resource_manager.service" ]]; then
    echo "Using custom service file name: ${CUSTOM_SERVICE_NAME}"
    SYSTEMD_SERVICE_FILE="/etc/systemd/system/${CUSTOM_SERVICE_NAME}"
  fi
fi

# Check if we're going to use custom service file content
if [[ "${UPDATE_SERVICE_FILE}" == "true" ]]; then
  echo "Updating systemd service file at ${SYSTEMD_SERVICE_FILE}..."
  
  # Create basic service file
  cat <<EOF > "${SYSTEMD_SERVICE_FILE}"
[Unit]
Description=Resource Manager API Service
After=network.target
X-Metadata-API_Version=1.0.1

[Service]
Type=simple
User=${SERVICE_USER}
Group=${SERVICE_USER}
WorkingDirectory=${INSTALL_DIR}
# Using the virtual environment's Python to run the server script
ExecStart=${VENV_DIR}/bin/python ${INSTALL_DIR}/resource_manager_server.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

  # Check for custom service file content in config and append if found
  if [[ -f "${CONFIG_FILE}" ]] && grep -q "service_file_content" "${CONFIG_FILE}"; then
    echo "Found custom service file content, applying additional settings..."
    CUSTOM_CONTENT=$(grep -A 100 "service_file_content" "${CONFIG_FILE}" | 
                    grep -B 100 -m 1 -E "^\]|^\"\"\"" | 
                    grep -v "service_file_content" | 
                    sed 's/^[ \t]*//')
    
    # Apply custom content by appending to appropriate sections
    # ...implementation for parsing and applying custom content...
  fi
  
  # Set proper permissions
  chmod 644 "${SYSTEMD_SERVICE_FILE}"
fi

# Set ownership of the installation directory
echo "Setting ownership of ${INSTALL_DIR} to ${SERVICE_USER}..."
chown -R ${SERVICE_USER}:${SERVICE_USER} "${INSTALL_DIR}"

echo "Resource Manager server has been successfully updated."
