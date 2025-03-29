#!/bin/bash
# Description: This script collects detailed system information and allows calling specific information modules.
# Usage: sudo ./get_detailed.sh [module_name]
# Author: Murilo Teixeira - dev@murilo.etc.br

set -euo pipefail

# Print usage information
usage() {
  echo "Usage: $0 [module_name]"
  echo "Available modules:"
  echo "  os             - Operating system information"
  echo "  cpu            - CPU information"
  echo "  disk_usage     - Disk usage (df output)"
  echo "  disk_parts     - Disk partitions information"
  echo "  smart          - S.M.A.R.T. disk information"
  echo "  network        - Network interfaces information"
  echo "  routing        - Routing table information"
  echo "  connections    - TCP/UDP connections information"
  echo "  firewall       - Firewall rules information"
  echo "  all            - All of the above (writes to /opt/resource_manager/static_info.json)"
  exit 1
}

# --- OS Module ---
collect_os_info() {
  OS=$(grep '^NAME=' /etc/os-release | cut -d'"' -f2)
  OS_VERSION=$(grep '^VERSION_ID=' /etc/os-release | cut -d'"' -f2)
  OS_NAME=$(grep '^VERSION_CODENAME=' /etc/os-release | cut -d'=' -f2)
  KERNEL=$(uname -r)
  HOSTNAME=$(uname -n)
  PLATFORM=$(uname -s)
  
  echo '{'
  echo '  "OS": {'
  echo '    "OS": "'$OS'",'
  echo '    "OS Version": "'$OS_VERSION'",'
  echo '    "OS Name": "'$OS_NAME'",'
  echo '    "Kernel": "'$KERNEL'",'
  echo '    "Hostname": "'$HOSTNAME'",'
  echo '    "Platform": "'$PLATFORM'"'
  echo '  }'
  echo '}'
}

# --- CPU Module ---
collect_cpu_info() {
  CPU_INFO=$(lscpu | awk -F: '
    /Flags:/ { next }
    {
      key = $1;
      sub(/^[ \t]+/, "", key);
      sub(/[ \t]+$/, "", key);
      
      value = $2;
      sub(/^[ \t]+/, "", value);
      sub(/[ \t]+$/, "", value);
      
      if (NR > 1) printf(",\n");
      printf("    \"%s\": \"%s\"", key, value);
    }
  ')
  
  echo '{'
  echo '  "Core": {'
  echo "$CPU_INFO"
  echo '  }'
  echo '}'
}

# --- Disk Usage Module (df) ---
collect_disk_usage() {
  # Get disk usage information, excluding tmpfs, udev, and loop devices
  DF_OUTPUT=$(df -h | grep -v "tmpfs\|udev\|loop")
  
  echo '{'
  
  # Check if we found any disk usage information
  if [ -z "$DF_OUTPUT" ] || [ "$(echo "$DF_OUTPUT" | wc -l)" -le 1 ]; then
    echo '  "DiskUsage": []'
    echo '}'
    return
  fi
  
  DISK_INFO=$(echo "$DF_OUTPUT" | awk 'NR>1 {
    printf("    {\n");
    printf("      \"Filesystem\": \"%s\",\n", $1);
    printf("      \"Size\": \"%s\",\n", $2);
    printf("      \"Used\": \"%s\",\n", $3);
    printf("      \"Avail\": \"%s\",\n", $4);
    printf("      \"Use%%\": \"%s\",\n", $5);
    printf("      \"Path\": \"%s\"\n", $6);
    if (NR < cmd) printf("    },\n"); else printf("    }\n");
  }' cmd="$(echo "$DF_OUTPUT" | grep -v "tmpfs\|udev\|loop" | wc -l)")
  
  echo '  "DiskUsage": ['
  echo "$DISK_INFO"
  echo '  ]'
  echo '}'
}

# --- Fixed Disk Partitions Module (fdisk) ---
collect_disk_partitions() {
  # Get list of disks (excluding loopback devices)
  DISKS=$(lsblk -d -n -o NAME | grep -v "loop")
  
  echo '{'
  
  # Check if we found any disks
  if [ -z "$DISKS" ]; then
    echo '  "Disks": []'
    echo '}'
    return
  fi
  
  echo '  "Disks": ['
  
  # Process each disk
  DISK_COUNT=$(echo "$DISKS" | wc -l)
  CURRENT=0
  
  for DISK in $DISKS; do
    CURRENT=$((CURRENT+1))
    
    # Get disk info using fdisk to get accurate labels and identifiers
    DISK_INFO=$(fdisk -l "/dev/$DISK" 2>/dev/null)
    DISK_SIZE=$(echo "$DISK_INFO" | grep "Disk /dev/$DISK:" | awk '{print $3" "$4}' | sed 's/,//')
    DISK_MODEL=$(lsblk -d -n -o MODEL "/dev/$DISK" | sed 's/\"//g')
    
    # Get partition table type and UUID 
    DISK_LABEL_TYPE=$(echo "$DISK_INFO" | grep "Disklabel type:" | awk '{print $3}')
    DISK_UUID=$(echo "$DISK_INFO" | grep "Disk identifier:" | awk '{print $3}')
    
    # Start disk object
    echo '    {'
    echo '      "Disk": "/dev/'$DISK'",'
    if [ ! -z "$DISK_SIZE" ]; then
      echo '      "Size": "'$DISK_SIZE'",'
    else
      # Fallback to lsblk if fdisk doesn't provide size
      DISK_SIZE=$(lsblk -d -n -o SIZE "/dev/$DISK")
      echo '      "Size": "'$DISK_SIZE'",'
    fi
    if [ ! -z "$DISK_MODEL" ]; then
      echo '      "Model": "'$DISK_MODEL'",'
    fi
    if [ ! -z "$DISK_LABEL_TYPE" ]; then
      echo '      "Disklabel type": "'$DISK_LABEL_TYPE'",'
    fi
    if [ ! -z "$DISK_UUID" ]; then
      echo '      "Disk identifier": "'$DISK_UUID'",'
    fi
    
    # Extract partitions information directly from fdisk output
    PARTS_INFO=$(echo "$DISK_INFO" | grep -A 100 "^Device" | grep "^/dev/$DISK" | sort)
    
    # Add partitions array
    echo '      "Devs": ['
    
    if [ ! -z "$PARTS_INFO" ]; then
      PART_COUNT=$(echo "$PARTS_INFO" | wc -l)
      PART_CURRENT=0
      
      echo "$PARTS_INFO" | while read -r LINE; do
        PART_CURRENT=$((PART_CURRENT+1))
        
        # Parse partition information
        PART_DEVICE=$(echo "$LINE" | awk '{print $1}')
        PART_SIZE=$(echo "$LINE" | awk '{for(i=1;i<=NF;i++) if($i ~ /[0-9]+[GM]/) print $i}' | tail -1)
        
        # Get filesystem type (if available)
        PART_TYPE=$(lsblk -n -o FSTYPE "$PART_DEVICE" 2>/dev/null)
        if [ -z "$PART_TYPE" ]; then
          # Try to get type from fdisk
          PART_TYPE=$(echo "$LINE" | awk '{print $(NF)}')
        fi
        
        echo '        {'
        echo '          "Device": "'$PART_DEVICE'",'
        if [ ! -z "$PART_SIZE" ]; then
          echo '          "Size": "'$PART_SIZE'",'
        else
          # Use lsblk as fallback
          PART_SIZE=$(lsblk -n -o SIZE "$PART_DEVICE" 2>/dev/null)
          echo '          "Size": "'$PART_SIZE'",'
        fi
        if [ ! -z "$PART_TYPE" ]; then
          echo '          "Type": "'$PART_TYPE'"'
        else
          echo '          "Type": "unknown"'
        fi
        
        if [ $PART_CURRENT -lt $PART_COUNT ]; then
          echo '        },'
        else
          echo '        }'
        fi
      done
    fi
    
    echo '      ]'
    
    # Close disk object
    if [ $CURRENT -lt $DISK_COUNT ]; then
      echo '    },'
    else
      echo '    }'
    fi
  done
  
  # End the array
  echo '  ]'
  echo '}'
}

# --- Fixed S.M.A.R.T Module ---
collect_smart_info() {
  echo '{'
  echo '  "SMART": '
  
  # Check if smartctl is available AND executable
  if ! command -v smartctl &> /dev/null; then
    echo '{ "status": "smartctl not installed" }'
    echo '}'
    return
  fi
  
  # Check if we can actually run smartctl (requires root privileges)
  if ! smartctl --version &> /dev/null; then
    echo '{ "status": "smartctl requires root privileges" }'
    echo '}'
    return
  fi
  
  # Get physical disks
  DISKS=$(lsblk -d -n -o NAME | grep -v "loop\|sr")
  
  # Start the array
  echo '['
  
  # Process each disk
  DISK_COUNT=$(echo "$DISKS" | wc -l)
  CURRENT=0
  
  for DISK in $DISKS; do
    CURRENT=$((CURRENT+1))
    
    # Check if SMART is available on this disk
    SMART_AVAILABLE=$(smartctl -i "/dev/$DISK" 2>/dev/null | grep -i "SMART support is:" | tail -1)
    
    echo '    {'
    echo '      "Device": "/dev/'$DISK'",'
    
    if echo "$SMART_AVAILABLE" | grep -qi "Enabled"; then
      # Get basic health
      HEALTH=$(smartctl -H "/dev/$DISK" 2>/dev/null | grep -i "SMART overall-health" | awk '{print $NF}')
      
      echo '      "SMART_Available": true,'
      if [ ! -z "$HEALTH" ]; then
        echo '      "Health": "'$HEALTH'",'
      else
        echo '      "Health": "Unknown",'
      fi
      
      # Get some key attributes
      TEMP=$(smartctl -A "/dev/$DISK" 2>/dev/null | grep -i "Temperature" | head -1 | awk '{print $10}')
      POH=$(smartctl -A "/dev/$DISK" 2>/dev/null | grep -i "Power_On_Hours" | awk '{print $10}')
      
      if [ ! -z "$TEMP" ]; then
        echo '      "Temperature": "'$TEMP'",'
      fi
      if [ ! -z "$POH" ]; then
        echo '      "Power_On_Hours": "'$POH'"'
      else
        echo '      "Details": "Limited information available"'
      fi
    else
      echo '      "SMART_Available": false,'
      echo '      "Reason": "SMART not enabled or not supported"'
    fi
    
    # Close disk object
    if [ $CURRENT -lt $DISK_COUNT ]; then
      echo '    },'
    else
      echo '    }'
    fi
  done
  
  # End the array
  echo '  ]'
  echo '}'
}

# --- Network Interfaces Module ---
collect_network_interfaces() {
  echo '{'
  # Check if ifconfig is available, otherwise try ip
  if command -v ifconfig &> /dev/null; then
    NET_CMD="ifconfig"
  elif command -v ip &> /dev/null; then
    NET_CMD="ip addr show"
  else
    echo '  "NetworkInterfaces": { "status": "network tools not installed" }'
    echo '}'
    return
  fi
  
  # Process interfaces
  if [ "$NET_CMD" = "ifconfig" ]; then
    # Get list of interfaces
    INTERFACES=$(ifconfig | grep -E '^[a-zA-Z0-9]+:' | awk '{print $1}' | sed 's/://')
    
    # Check if we found any interfaces
    if [ -z "$INTERFACES" ]; then
      echo '  "NetworkInterfaces": { "status": "no network interfaces found" }'
      echo '}'
      return
    fi
    
    # Count for JSON formatting
    IFACE_COUNT=$(echo "$INTERFACES" | wc -l)
    CURRENT=0
    
    for IFACE in $INTERFACES; do
      CURRENT=$((CURRENT+1))
      
      # Get interface details
      IFDATA=$(ifconfig "$IFACE")
      
      # Extract relevant information
      MAC=$(echo "$IFDATA" | grep -o -E '([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}' | head -1)
      IP_V4=$(echo "$IFDATA" | grep 'inet ' | awk '{print $2}')
      MASK_V4=$(echo "$IFDATA" | grep 'inet ' | awk '{print $4}')
      IP_V6=$(echo "$IFDATA" | grep 'inet6' | awk '{print $2}')
      
      # Check if interface is up
      if echo "$IFDATA" | grep -q "UP"; then
        STATE="UP"
      else
        STATE="DOWN"
      fi
      
      echo '    {'
      echo '      "Interface": "'$IFACE'",'
      echo '      "State": "'$STATE'",'
      if [ ! -z "$MAC" ]; then
        echo '      "MAC": "'$MAC'",'
      fi
      if [ ! -z "$IP_V4" ]; then
        echo '      "IPv4": "'$IP_V4'",'
        if [ ! -z "$MASK_V4" ]; then
          echo '      "Netmask": "'$MASK_V4'",'
        fi
      fi
      if [ ! -z "$IP_V6" ]; then
        echo '      "IPv6": "'$IP_V6'"'
      elif [ ! -z "$IP_V4" ]; then
        # Remove trailing comma if IPv4 was the last entry
        sed -i '$ s/,$//' /tmp/net_temp 2>/dev/null || true
        echo '' # Continue with empty line
      else
        echo '      "No IP assigned": true'
      fi
      
      # Close interface object
      if [ $CURRENT -lt $IFACE_COUNT ]; then
        echo '    },'
      else
        echo '    }'
      fi
    done
  else
    # Using 'ip' command
    INTERFACES=$(ip -o link show | awk -F': ' '{print $2}')
    
    # Check if we found any interfaces
    if [ -z "$INTERFACES" ]; then
      echo '  "NetworkInterfaces": { "status": "no network interfaces found" }'
      echo '}'
      return
    fi
    
    # Count for JSON formatting
    IFACE_COUNT=$(echo "$INTERFACES" | wc -l)
    CURRENT=0
    
    for IFACE in $INTERFACES; do
      CURRENT=$((CURRENT+1))
      
      # Get interface details
      LINK_INFO=$(ip -o link show dev "$IFACE")
      ADDR_INFO=$(ip -o addr show dev "$IFACE" 2>/dev/null)
      
      # Extract relevant information
      MAC=$(echo "$LINK_INFO" | grep -o -E '([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}')
      
      # Check if interface is up
      if echo "$LINK_INFO" | grep -q "UP"; then
        STATE="UP"
      else
        STATE="DOWN"
      fi
      
      echo '    {'
      echo '      "Interface": "'$IFACE'",'
      echo '      "State": "'$STATE'",'
      if [ ! -z "$MAC" ]; then
        echo '      "MAC": "'$MAC'",'
      fi
      
      # Get IPv4 information
      IP_V4=$(echo "$ADDR_INFO" | grep 'inet ' | head -1 | awk '{print $4}')
      if [ ! -z "$IP_V4" ]; then
        echo '      "IPv4": "'$IP_V4'",'
      fi
      
      # Get IPv6 information
      IP_V6=$(echo "$ADDR_INFO" | grep 'inet6' | head -1 | awk '{print $4}')
      if [ ! -z "$IP_V6" ]; then
        echo '      "IPv6": "'$IP_V6'"'
      elif [ ! -z "$IP_V4" ]; then
        # Remove trailing comma if IPv4 was the last entry
        sed -i '$ s/,$//' /tmp/net_temp 2>/dev/null || true
        echo '' # Continue with empty line
      else
        echo '      "No IP assigned": true'
      fi
      
      # Close interface object
      if [ $CURRENT -lt $IFACE_COUNT ]; then
        echo '    },'
      else
        echo '    }'
      fi
    done
  fi
  
  # End the array
  echo '  ]'
  echo '}'
}

# --- Routing Table Module ---
collect_routing_table() {
  echo '{'
  # Check if route command is available
  if ! command -v route &> /dev/null; then
    echo '  "RoutingTable": { "status": "route command not available" }'
    echo '}'
    return
  fi
  
  # Get routing table using route -n
  ROUTES=$(route -n | tail -n +3)
  
  # Check if we found any routes
  if [ -z "$ROUTES" ]; then
    echo '  "RoutingTable": { "status": "no routes found" }'
    echo '}'
    return
  fi
  
  # Start the array
  echo '  "RoutingTable": ['
  
  # Count for JSON formatting
  ROUTE_COUNT=$(echo "$ROUTES" | wc -l)
  CURRENT=0
  
  echo "$ROUTES" | while read -r LINE; do
    CURRENT=$((CURRENT+1))
    
    # Extract route information
    DEST=$(echo "$LINE" | awk '{print $1}')
    GATEWAY=$(echo "$LINE" | awk '{print $2}')
    MASK=$(echo "$LINE" | awk '{print $3}')
    FLAGS=$(echo "$LINE" | awk '{print $4}')
    METRIC=$(echo "$LINE" | awk '{print $5}')
    IFACE=$(echo "$LINE" | awk '{print $8}')
    
    echo '    {'
    echo '      "Destination": "'$DEST'",'
    echo '      "Gateway": "'$GATEWAY'",'
    echo '      "Netmask": "'$MASK'",'
    echo '      "Flags": "'$FLAGS'",'
    echo '      "Metric": "'$METRIC'",'
    echo '      "Interface": "'$IFACE'"'
    echo -n '    }'
    
    if [ $CURRENT -lt $ROUTE_COUNT ]; then
      echo ','
    else
      echo ''
    fi
  done
  
  # End the array
  echo '  ]'
  echo '}'
}

# --- TCP/UDP Connections Module ---
collect_tcp_udp_connections() {
  echo '{'
  # Check if netstat command is available
  if ! command -v netstat &> /dev/null; then
    echo '  "Connections": { "status": "netstat command not available" }'
    echo '}'
    return
  fi
  
  # Attempt to run netstat, handling permissions
  NETSTAT_OUT=$(netstat -tulpn 2>/dev/null)
  if [ $? -ne 0 ] || [ -z "$NETSTAT_OUT" ]; then
    echo '  "Connections": { "status": "insufficient permissions, try running as root" }'
    echo '}'
    return
  fi
  
  # Parse netstat output, skipping headers
  CONNECTIONS=$(echo "$NETSTAT_OUT" | tail -n +3)
  
  # Check if we found any connections
  if [ -z "$CONNECTIONS" ]; then
    echo '  "Connections": { "status": "no active connections found" }'
    echo '}'
    return
  fi
  
  # Start the array
  echo '  "Connections": ['
  
  # Count for JSON formatting
  CONNECTION_COUNT=$(echo "$CONNECTIONS" | wc -l)
  CURRENT=0
  
  echo "$CONNECTIONS" | while read -r LINE; do
    CURRENT=$((CURRENT+1))
    
    # Extract connection information
    PROTO=$(echo "$LINE" | awk '{print $1}')
    LOCAL_ADDR=$(echo "$LINE" | awk '{print $4}')
    FOREIGN_ADDR=$(echo "$LINE" | awk '{print $5}')
    STATE=$(echo "$LINE" | awk '{print $6}')
    PID_PROG=$(echo "$LINE" | awk '{print $7}')
    
    echo '    {'
    echo '      "Protocol": "'$PROTO'",'
    echo '      "Local Address": "'$LOCAL_ADDR'",'
    echo '      "Foreign Address": "'$FOREIGN_ADDR'",'
    if [ "$PROTO" != "udp" ] && [ "$PROTO" != "udp6" ]; then
      echo '      "State": "'$STATE'",'
    fi
    if [ "$PID_PROG" != "-" ] && [ ! -z "$PID_PROG" ]; then
      echo '      "PID/Program": "'$PID_PROG'"'
    else
      echo '      "PID/Program": "unknown"'
    fi
    
    # Close connection object
    if [ $CURRENT -lt $CONNECTION_COUNT ]; then
      echo '    },'
    else
      echo '    }'
    fi
  done
  
  # End the array
  echo '  ]'
  echo '}'
}

# --- Firewall Rules Module ---
collect_firewall_rules() {
  echo '{'
  # Check if iptables command is available
  if ! command -v iptables &> /dev/null; then
    echo '  "FirewallRules": { "status": "iptables command not available" }'
    echo '}'
    return
  fi
  
  # Attempt to run iptables
  IPTABLES_OUT=$(iptables -S 2>/dev/null)
  if [ $? -ne 0 ] || [ -z "$IPTABLES_OUT" ]; then
    echo '  "FirewallRules": { "status": "insufficient permissions, try running as root" }'
    echo '}'
    return
  fi
  
  # Start the object
  echo '  "FirewallRules": {'
  
  # Get all chains
  CHAINS=$(echo "$IPTABLES_OUT" | grep -E "^-N|^-P" | awk '{print $2}' | sort | uniq)
  
  # Check if we found any chains
  if [ -z "$CHAINS" ]; then
    echo '    "status": "no firewall chains found"'
    echo '  }'
    echo '}'
    return
  fi
  
  # Count for JSON formatting
  CHAIN_COUNT=$(echo "$CHAINS" | wc -l)
  CURRENT=0
  
  for CHAIN in $CHAINS; do
    CURRENT=$((CURRENT+1))
    
    # Get rules for this chain
    RULES=$(echo "$IPTABLES_OUT" | grep -E "^-A $CHAIN")
    
    echo '    "'$CHAIN'": ['
    
    # Process rules for the current chain
    RULE_COUNT=$(echo "$RULES" | wc -l)
    RULE_CURRENT=0
    
    echo "$RULES" | while read -r RULE; do
      RULE_CURRENT=$((RULE_CURRENT+1))
      
      # Remove the first two fields (-A CHAIN)
      RULE_CONTENT=$(echo "$RULE" | cut -d' ' -f3-)
      
      echo '      "'$RULE_CONTENT'"'
      
      if [ $RULE_CURRENT -lt $RULE_COUNT ]; then
        echo '      ,'
      fi
    done
    
    echo '    ]'
    
    # Add comma if not the last chain
    if [ $CURRENT -lt $CHAIN_COUNT ]; then
      echo '    ,'
    fi
  done
  
  # End the object
  echo '  }'
  echo '}'
}

# --- Main Execution Function ---
collect_all() {
  OUTFILE="/opt/resource_manager/static_info.json"
  mkdir -p "$(dirname "$OUTFILE")"
  
  {
    echo '{'
    
    # Collect each module, ensuring valid JSON for all sections
    # OS info should always be available
    TMP_OS=$(collect_os_info | grep -v -E "^\{|\}$")
    echo "$TMP_OS,"
    
    # CPU info should always be available
    TMP_CPU=$(collect_cpu_info | grep -v -E "^\{|\}$")
    echo "$TMP_CPU,"
    
    # These modules will handle their own empty cases
    TMP_DISK_USAGE=$(collect_disk_usage | grep -v -E "^\{|\}$")
    echo "$TMP_DISK_USAGE,"
    
    TMP_DISK_PARTS=$(collect_disk_partitions | grep -v -E "^\{|\}$")
    echo "$TMP_DISK_PARTS,"
    
    TMP_SMART=$(collect_smart_info | grep -v -E "^\{|\}$")
    echo "$TMP_SMART,"
    
    TMP_NETWORK=$(collect_network_interfaces | grep -v -E "^\{|\}$")
    echo "$TMP_NETWORK,"
    
    TMP_ROUTING=$(collect_routing_table | grep -v -E "^\{|\}$")
    echo "$TMP_ROUTING,"
    
    TMP_CONNECTIONS=$(collect_tcp_udp_connections | grep -v -E "^\{|\}$")
    echo "$TMP_CONNECTIONS,"
    
    TMP_FIREWALL=$(collect_firewall_rules | grep -v -E "^\{|\}$")
    echo "$TMP_FIREWALL"
    
    echo '}'
  } > "${OUTFILE}"
  
  # Validate the JSON output if possible
  if command -v python3 &> /dev/null; then
    if ! python3 -m json.tool "${OUTFILE}" > /dev/null 2>&1; then
      echo "Warning: Generated JSON may not be valid. Attempting to fix..."
      echo '{"status": "error generating complete system information"}' > "${OUTFILE}"
    fi
  fi
  
  echo "Written complete system information to ${OUTFILE}"
}

# --- Individual module execution with validation ---
execute_module() {
  MODULE_NAME="$1"
  OUTPUT=$(eval "collect_${MODULE_NAME}")
  
  # Validate the JSON output if possible
  if command -v python3 &> /dev/null; then
    if ! echo "$OUTPUT" | python3 -m json.tool > /dev/null 2>&1; then
      echo '{"status": "error generating '"${MODULE_NAME}"' information"}'
      return
    fi
  fi
  
  echo "$OUTPUT"
}

# --- Main Script Execution ---
# Check if we have a parameter
if [ $# -eq 0 ]; then
  usage
fi

# Handle different module requests
case "$1" in
  "os")
    execute_module "os_info"
    ;;
  "cpu")
    execute_module "cpu_info"
    ;;
  "disk_usage")
    execute_module "disk_usage"
    ;;
  "disk_parts")
    execute_module "disk_partitions"
    ;;
  "smart")
    execute_module "smart_info"
    ;;
  "network")
    execute_module "network_interfaces"
    ;;
  "routing")
    execute_module "routing_table"
    ;;
  "connections")
    execute_module "tcp_udp_connections"
    ;;
  "firewall")
    execute_module "firewall_rules"
    ;;
  "all")
    collect_all
    ;;
  *)
    echo "Error: Unknown module '$1'"
    usage
    ;;
esac

exit 0
