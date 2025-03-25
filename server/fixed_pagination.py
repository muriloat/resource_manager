import subprocess
import logging
import re
from math import ceil

logger = logging.getLogger(__name__)

def count_total_journal_entries(service_name, since="24 hours ago"):
    """Count the total number of journal entries for a service."""
    try:
        # Command to count all entries without pagination limits
        cmd = [
            "bash", "-c",
            f"journalctl -u {service_name}.service --since '{since}' --no-pager --quiet | wc -l"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            count_str = result.stdout.strip()
            return int(count_str)
        else:
            logger.warning(f"Error counting journal entries: {result.stderr}")
            return 0
    except Exception as e:
        logger.error(f"Exception counting journal entries: {e}")
        return 0

def get_paginated_journal_logs(service_name, page=1, per_page=50, since="24 hours ago"):
    """
    Get paginated journal logs using standard Unix tools rather than journalctl's
    pagination options which might not be available on all systems.
    
    Args:
        service_name: Name of the service to get logs for
        page: Page number (1-based)
        per_page: Number of entries per page
        since: Time specification for log retrieval
        
    Returns:
        dict: Dictionary containing logs and pagination metadata
    """
    try:
        # Get total count for pagination info
        total_logs = count_total_journal_entries(service_name, since)
        
        # Calculate pagination values
        page = max(1, int(page))
        per_page = max(1, int(per_page))
        total_pages = ceil(total_logs / per_page) if total_logs > 0 else 1
        
        # Use head and tail to implement pagination
        # For example, for page 2 with 50 per page:
        # - We need entries 51-100
        # - Use "tail -n +51" to get entries starting from 51
        # - Use "head -n 50" to limit to 50 entries
        
        start_line = (page - 1) * per_page + 1
        
        # Construct journalctl command with pagination
        cmd = [
            "bash", "-c",
            f"sudo journalctl -u {service_name}.service --since '{since}' --no-pager | "
            f"tail -n +{start_line} | head -n {per_page}"
        ]
        
        logger.info(f"Executing paginated journalctl: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        # Parse log entries
        log_entries = []
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                # Skip empty lines
                if not line.strip():
                    continue
                
                # Create log entry dictionary
                log_entry = {"raw": line}
                
                # Try to parse the log line format
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
                    logger.warning(f"Error parsing log line: {e}")
                
                log_entries.append(log_entry)
        
        # Create pagination info
        pagination = {
            "page": page,
            "per_page": per_page,
            "total_logs": total_logs,
            "total_pages": total_pages,
            "has_prev": page > 1,
            "has_next": page < total_pages
        }
        
        # Return structured response
        return {
            "logs": log_entries,
            "log_count": len(log_entries),
            "pagination": pagination,
            "command": " ".join(cmd),
            "exit_code": result.returncode,
            "error": result.stderr if result.stderr else None
        }
    
    except Exception as e:
        logger.error(f"Error retrieving paginated logs: {e}")
        return {
            "logs": [],
            "log_count": 0,
            "error": str(e),
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total_logs": 0,
                "total_pages": 1,
                "has_prev": False,
                "has_next": False
            }
        }
