import time
import curses
import logging
from typing import Dict, Any, List, Tuple, Optional
from .service_manager import ShellServiceManager

class Terminal:
    """Terminal UI handler for service management."""
    
    # Color definitions for consistent UI rendering
    COLORS = {
        'header': 1,
        'status_ok': 2,
        'status_error': 3,
        'highlight': 4,
        'normal': 5,
        'selected': 6,
    }
    
    # Key code constants for better readability
    KEY_ESC = 27
    KEY_ENTER = 10
    KEY_SPACE = 32
    KEY_r = 114
    KEY_q = 113
    KEY_f = 102
    KEY_g = 103
    KEY_h = 104
    KEY_l = 108
    KEY_SLASH = 47
    
    def __init__(self, config, logger=None):
        """Initialize the terminal interface.
        
        Args:
            config: Configuration object
            logger: Optional logger instance
        """
        self.config = config
        self.logger = logger or logging.getLogger(__name__)
        self.managers = {}  # Dict of host_id -> ShellServiceManager
        
        # Ensure we have at least one default host
        self.config.ensure_default_host()

        # Initialize the service manager for the active host
        self._initialize_current_manager()

        # Screen properties
        self.stdscr = None
        self.height = 0
        self.width = 0
        
        # UI state
        self.current_row = 0
        self.scroll_offset = 0
        self.status_message = ""
        self.status_time = 0
        self.view_mode = "list"  # list, details, logs, hosts
        self.current_service = None
        self.current_server = None
        self.current_col = 0
        self.cols = ["State", "Boot"]  # Columns that can be toggled
        self.filter_mode = False
        self.filter_input = ""
        self.should_exit = False

    def _initialize_current_manager(self):
        """Initialize the service manager for the current host."""
        host_id = self.config.get_current_host_id()
        
        if host_id not in self.managers:
            try:
                host_config = self.config.get_client_config(host_id)
                tool_settings = self.config.get_tool_settings()
                
                self.logger.debug(f"Initializing service manager for host: {host_id}")
                
                # Create combined config for ShellServiceManager
                combined_config = {
                    'BASE_URL': host_config.get('base_url', 'http://localhost:5000'),
                    'TIMEOUT': host_config.get('timeout', 10),
                    'REFRESH_INTERVAL': tool_settings.get('refresh_interval', 10),
                    'LOG_LINES': tool_settings.get('log_lines', 25),
                    'LOG_TIME_RANGE': tool_settings.get('log_time_range', '30 minutes ago'),
                }
                
                # Create manager with logger
                self.managers[host_id] = ShellServiceManager(combined_config, self.logger, self.config)
            
                # Check connectivity before continuing
                health = self.managers[host_id].check_server_health()
                if "error" in health:
                    self.managers[host_id].is_reachable = False
                    self.logger.error(f"Host {host_id} is unreachable: {health.get('error')}")
                    raise ConnectionError(f"Host {host_id} is unreachable: {health.get('error')}")
                    
                # Initialize data if reachable
                self.logger.debug("Loading initial data for new manager")
                self.managers[host_id].load_all_data()
                
            except Exception as e:
                self.logger.error(f"Error initializing manager for {host_id}: {e}")
                # If this host is the only one we have, don't remove it, but mark it as unreachable
                if host_id in self.managers:
                    self.managers[host_id].is_reachable = False
                
                # Fallback to another host if possible
                if host_id != "default" and "default" in self.config.get_all_hosts():
                    self.logger.warning("Falling back to default host")
                    self.config.set_current_host_id("default")
                    return self._initialize_current_manager()
                else:
                    # If we can't fall back, keep it but indicate it's unreachable
                    self.logger.critical(f"No fallback host available after failing to connect to {host_id}")
                    raise RuntimeError(f"Host {host_id} is unreachable and no fallback is available")

        # Set current manager
        if host_id in self.managers:
            self.current_manager = self.managers[host_id]
        else:
            self.logger.critical("No valid service manager could be initialized")
            raise RuntimeError("Failed to initialize service manager")
    
    def switch_host(self, host_id):
        """Switch to a different host."""
        if host_id != self.config.get_current_host_id():
            # Check if this host is known to be unreachable before switching
            if host_id in self.managers:
                controller = self.managers[host_id]
                if hasattr(controller, 'is_reachable') and not controller.is_reachable:
                    self.set_status(f"Cannot switch to unreachable host: {host_id}", error=True)
                    return False
                    
            # Attempt to switch
            if self.config.set_current_host_id(host_id):
                self.logger.info(f"Switched to host: {host_id}")
                try:
                    self._initialize_current_manager()
                    # If we get here, the initialization was successful
                    return True
                except Exception as e:
                    # Revert the change if initialization fails
                    self.logger.error(f"Failed to initialize manager for {host_id}: {e}")
                    self.config.set_current_host_id(self.current_manager.full_config.get_current_host_id())
                    self.set_status(f"Failed to switch to host {host_id}: {str(e)}", error=True)
                    return False
        return False
    
    def draw_hosts_view(self):
        """Draw the hosts management view."""
        # Clear screen content before drawing
        self._clear_content_area()
        self.draw_header("Hosts Management")
        
        hosts = self.config.get_all_hosts()
        current_host = self.config.get_current_host_id()
        
        if not hosts:
            self.safe_addstr(1, 1, "No hosts configured. Press 'A' to add a new host.")
            return
            
        row = 1
        host_ids = list(hosts.keys())  # Convert to list to ensure consistent order
        
        for i, host_id in enumerate(host_ids):
            if row >= self.height - 1:
                break
            
            host_config = hosts.get(host_id, {})
                
            # Highlight the current row or active host
            if i == self.current_row:
                attr = curses.color_pair(self.COLORS['selected'])
            elif host_id == current_host:
                attr = curses.color_pair(self.COLORS['highlight'])
            else:
                attr = curses.color_pair(self.COLORS['normal'])
                
            self.stdscr.attron(attr)
            
            # Display host information
            self.safe_addstr(row, 1, f"{host_id}")
            self.safe_addstr(row, 20, f"{host_config.get('base_url', 'N/A')}")
            
            # Show connection status
            status = "Not connected"
            status_attr = attr
            try:
                if host_id in self.managers:
                    controller = self.managers[host_id]
                    
                    # Check if we've already determined reachability
                    if hasattr(controller, 'is_reachable') and not controller.is_reachable:
                        status = "Offline"
                        status_attr = curses.color_pair(self.COLORS['status_error'])
                    else:
                        # Try to get health status
                        health = controller.check_server_health()
                        if "error" in health:
                            status = f"Error: {health.get('error', 'Unknown')}"
                            status_attr = curses.color_pair(self.COLORS['status_error'])
                        elif health.get('status') == 'healthy':
                            status = "Connected"
                            status_attr = curses.color_pair(self.COLORS['status_ok'])
                        else:
                            status = "Unhealthy"
                            status_attr = curses.color_pair(self.COLORS['status_error'])
                else:
                    status = "Not initialized"
            except Exception:
                status = "Unreachable"
                status_attr = curses.color_pair(self.COLORS['status_error'])
            
            # Draw the base information with standard attributes
            self.safe_addstr(row, 50, "           ")  # Clear the space first
            
            # Switch to status-specific color for the status text
            self.stdscr.attroff(attr)
            self.stdscr.attron(status_attr)
            self.safe_addstr(row, 50, status)
            self.stdscr.attroff(status_attr)
            self.stdscr.attron(attr)
                
            self.stdscr.attroff(attr)
            
            row += 1
        
        # Instructions
        row = self.height - 3
        self.safe_addstr(row, 1, "Enter: Select host | A: Add host | D: Delete host | Esc: Back")
    
    def handle_hosts_input(self, key):
        """Handle keyboard input for the hosts view."""
        hosts = list(self.config.get_all_hosts().keys())
        
        # If no hosts configured, force creation of a new one
        if len(hosts) == 0:
            self.add_new_host()
            return
        
        if key == curses.KEY_UP:
            if self.current_row > 0:
                self.current_row -= 1
                
        elif key == curses.KEY_DOWN:
            if self.current_row < len(hosts) - 1:
                self.current_row += 1
                
        elif key in [self.KEY_ENTER, 10, 13, ord('\n')]:  # Support different Enter key codes
            # Switch to selected host
            if 0 <= self.current_row < len(hosts):
                host_id = hosts[self.current_row]
                
                # Check if the host is already known to be unreachable
                if host_id in self.managers:
                    controller = self.managers[host_id]
                    if hasattr(controller, 'is_reachable') and not controller.is_reachable:
                        self.set_status(f"Cannot switch to unreachable host: {host_id}", error=True)
                        return
                
                # Try to switch
                if self.switch_host(host_id):
                    self.view_mode = "list"
                    self.current_row = 0
                    self.scroll_offset = 0
                
        elif key in [ord('a'), ord('A')]:
            # Add new host functionality
            self.add_new_host()
            
        elif key in [ord('d'), ord('D')]:
            # Delete selected host
            if 0 <= self.current_row < len(hosts):
                host_id = hosts[self.current_row]
                if host_id != "default":  # Prevent deleting default
                    self.delete_host(host_id)
        
        elif key == self.KEY_ESC:
            self.view_mode = "list"    

    def add_new_host(self):
        """Display a dialog to add a new host configuration."""
        # First get the host ID
        host_id = self.text_input_dialog(
            "Add New Host", 
            "Enter a unique ID for this host:",
            max_length=20
        )
        
        if host_id is None or host_id.strip() == "":
            self.set_status("Host creation cancelled", error=True)
            return
        
        # Check if ID already exists
        if host_id in self.config.get_all_hosts():
            self.set_status(f"Host ID '{host_id}' already exists", error=True)
            return
        
        # Get the host URL
        url = self.text_input_dialog(
            "Add New Host", 
            f"Enter the base URL for host '{host_id}':",
            default_text="http://localhost:5000"
        )
        
        if url is None or url.strip() == "":
            self.set_status("Host creation cancelled", error=True)
            return
        
        # Get timeout
        timeout_str = self.text_input_dialog(
            "Add New Host", 
            "Enter request timeout in seconds:",
            default_text="10",
            max_length=3
        )
        
        if timeout_str is None:
            self.set_status("Host creation cancelled", error=True)
            return
        
        # Validate timeout
        try:
            timeout = int(timeout_str)
            if timeout <= 0:
                raise ValueError("Timeout must be positive")
        except ValueError:
            self.set_status("Invalid timeout value, using default of 10", error=True)
            timeout = 10
        
        # Create the new host configuration
        new_host_config = {
            "base_url": url,
            "timeout": timeout,
            "verify_ssl": True
        }
        
        # Add to configuration
        if self.config.client_config.set_host_config(host_id, new_host_config):
            self.set_status(f"Host '{host_id}' added successfully")
            
            # Refresh the hosts list
            self.current_row = 0  # Reset selection to top
        else:
            self.set_status("Failed to save host configuration", error=True)

    def delete_host(self, host_id):
        """Delete a host configuration after confirmation."""
        if host_id == "default":
            self.set_status("Cannot delete the default host", error=True)
            return False
        
        # Ask for confirmation
        message = [
            f"Are you sure you want to delete host '{host_id}'?",
            "",
            "This action cannot be undone."
        ]
        
        result = self.show_dialog("Confirm Deletion", message, ["Delete", "Cancel"], default_option=1)
        
        if result != 0:  # Not confirmed
            self.set_status("Host deletion cancelled")
            return False
        
        # Delete the host
        if self.config.client_config.remove_host(host_id):
            self.set_status(f"Host '{host_id}' deleted successfully")
            
            # If we were viewing the deleted host, switch to default
            if host_id == self.config.get_current_host_id():
                self.config.set_current_host_id("default")
                self._initialize_current_manager()
            
            # Reset selection position
            self.current_row = 0
            return True
        else:
            self.set_status("Failed to delete host configuration", error=True)
            return False

    def _clear_content_area(self):
        """Clear the main content area of the screen."""
        try:
            for i in range(1, self.height-1):
                self.stdscr.move(i, 0)
                self.stdscr.clrtoeol()
        except curses.error:
            pass
            
    def text_input_dialog(self, title, prompt, default_text="", max_length=50):
        """Display a text input dialog to get user input."""
        # Save current screen state
        curses.def_prog_mode()
        
        # Prepare dialog dimensions
        dialog_height = 6
        dialog_width = max(50, len(prompt) + 10, len(title) + 10)
        dialog_y = (self.height - dialog_height) // 2
        dialog_x = (self.width - dialog_width) // 2
        
        # Create dialog window
        dialog = curses.newwin(dialog_height, dialog_width, dialog_y, dialog_x)
        dialog.keypad(True)
        
        # Initialize text input
        current_text = default_text
        cursor_pos = len(current_text)
        
        # Input field position
        input_y = 3
        input_x = 2
        field_width = dialog_width - 4
        
        # Function to draw the dialog
        def draw_dialog():
            dialog.erase()
            dialog.box()
            
            # Title
            title_x = (dialog_width - len(title)) // 2
            dialog.addstr(0, title_x, title)
            
            # Prompt
            dialog.addstr(1, 2, prompt)
            
            # Input field
            dialog.addstr(input_y, input_x, " " * field_width)
            
            # Display text with cursor
            display_start = max(0, cursor_pos - field_width + 5)
            visible_text = current_text[display_start:display_start + field_width - 1]
            dialog.addstr(input_y, input_x, visible_text)
            
            # Instructions
            dialog.addstr(dialog_height - 2, 2, "Enter to confirm, ESC to cancel")
            
            # Position cursor
            cursor_x = input_x + cursor_pos - display_start
            if cursor_x < dialog_width - 1:
                try:
                    dialog.move(input_y, cursor_x)
                except curses.error:
                    pass
            
            dialog.refresh()
        
        # Main input loop
        try:
            curses.curs_set(1)  # Show cursor
            
            while True:
                draw_dialog()
                
                key = dialog.getch()
                
                if key in [10, 13]:  # Enter
                    return current_text
                    
                elif key == 27:  # ESC
                    return None
                    
                elif key == curses.KEY_LEFT and cursor_pos > 0:
                    cursor_pos -= 1
                    
                elif key == curses.KEY_RIGHT and cursor_pos < len(current_text):
                    cursor_pos += 1
                    
                elif key == curses.KEY_HOME:
                    cursor_pos = 0
                    
                elif key == curses.KEY_END:
                    cursor_pos = len(current_text)
                    
                elif key in [curses.KEY_BACKSPACE, 127]:  # Backspace
                    if cursor_pos > 0:
                        current_text = current_text[:cursor_pos-1] + current_text[cursor_pos:]
                        cursor_pos -= 1
                        
                elif key == curses.KEY_DC:  # Delete key
                    if cursor_pos < len(current_text):
                        current_text = current_text[:cursor_pos] + current_text[cursor_pos+1:]
                        
                elif 32 <= key <= 126 and len(current_text) < max_length:  # Printable ASCII
                    current_text = current_text[:cursor_pos] + chr(key) + current_text[cursor_pos:]
                    cursor_pos += 1
        
        finally:
            curses.curs_set(0)  # Hide cursor
            curses.reset_prog_mode()
            self.stdscr.clear()
            self.stdscr.refresh()
            
        return None  # Fallback

    def setup_colors(self):
        """Initialize color pairs for the UI."""
        try:
            curses.start_color()
            curses.use_default_colors()
            curses.init_pair(self.COLORS['header'], curses.COLOR_BLACK, curses.COLOR_CYAN)
            curses.init_pair(self.COLORS['status_ok'], curses.COLOR_GREEN, -1)
            curses.init_pair(self.COLORS['status_error'], curses.COLOR_RED, -1)
            curses.init_pair(self.COLORS['highlight'], curses.COLOR_CYAN, -1)
            curses.init_pair(self.COLORS['normal'], -1, -1)
            curses.init_pair(self.COLORS['selected'], curses.COLOR_BLACK, curses.COLOR_WHITE)
        except Exception as e:
            self.logger.error(f"Error setting up colors: {e}")
        
    def set_status(self, message, error=False):
        """Set a status message with timestamp."""
        self.status_message = message
        self.status_time = time.time()
        try:
            color = curses.color_pair(self.COLORS['status_error'] if error else self.COLORS['status_ok'])
            self.draw_status_bar(color)
        except Exception as e:
            self.logger.error(f"Error setting status: {e}")
        
    def draw_status_bar(self, color=None):
        """Draw the status bar at the bottom of the screen."""
        if self.stdscr is None:
            return
            
        try:
            if color is None:
                color = curses.color_pair(self.COLORS['normal'])
                
            self.stdscr.attron(color)
            self.stdscr.hline(self.height-1, 0, ' ', self.width)
            
            # Show refresh countdown
            now = time.time()
            time_since_refresh = now - self.current_manager.last_refresh
            refresh_interval = self.config.get_setting("refresh_interval", 10)
            refresh_in = max(0, int(refresh_interval - time_since_refresh))
            refresh_text = f"Refresh in: {refresh_in}s"
            
            # Show status message if it's recent (< 5 seconds)
            if time.time() - self.status_time < 5 and self.status_message:
                self.safe_addstr(self.height-1, 1, f"{self.status_message[:self.width-len(refresh_text)-5]} | {refresh_text}")
            else:
                # Otherwise show contextual help based on current view
                if self.view_mode == "list":
                    help_text = "↑/↓:Navigate | Enter:Select | ←/→:Move | Space:Toggle | F:Filter | R:Reload | Q:Quit | H:Hosts"
                elif self.view_mode == "details":
                    help_text = "↑/↓:Scroll | L:View Logs | R:Restart | G:Reload Service | B:Back | Q:Quit"
                elif self.view_mode == "logs":
                    help_text = "↑/↓:Scroll | B:Back | Q:Quit"
                else:  # hosts view
                    help_text = "↑/↓:Navigate | Enter:Select | A:Add Host | D:Delete Host | Esc:Back | Q:Quit"
                    
                self.safe_addstr(self.height-1, 1, f"{help_text[:self.width-len(refresh_text)-5]} | {refresh_text}")
                
            self.stdscr.attroff(color)
        except Exception as e:
            self.logger.error(f"Error drawing status bar: {e}")

    def draw_header(self, title=None):
        """Draw the header row with column names or a title."""
        try:
            # First, clear the entire header line
            self.stdscr.move(0, 0)
            self.stdscr.clrtoeol()

            # Apply header color
            header = curses.color_pair(self.COLORS['header'])
            self.stdscr.attron(header)

            # Fill the entire width with the header background color
            self.stdscr.hline(0, 0, ' ', self.width)
            
            if title:
                # Draw centered title
                x = (self.width - len(title)) // 2
                if x > 0:
                    self.stdscr.addstr(0, x, title)
            else:
                # Column headers
                col_headers = [
                    "Service",
                    "Host",
                    "VM",
                    "IP",
                    "Project",
                    "PID",
                    "CPU",
                    "Mem",
                    "State",
                    "Boot",
                    "Uptime",
                    "Logs"
                ]
                
                # Column positions (approximate)
                pos = 0
                for i, col in enumerate(col_headers):
                    if pos > self.width:
                        break
                        
                    width = 8  # Default width
                    if i == 0:  # Service name
                        width = 25
                    elif i == 1:  # Host
                        width = 20
                    elif i == 2:  # VM
                        width = 20
                    elif i == 3:  # IP
                        width = 15
                    elif i == 4:  # Project
                        width = 15
                    
                    self.safe_addstr(0, pos, col[:width].center(width))
                    pos += width + 1

            self.stdscr.attroff(header)
        except curses.error:
            pass

    def draw_filter_prompt(self):
        """Draw the filter input prompt."""
        try:
            prompt = f"Filter: {self.filter_input}"
            self.stdscr.attron(curses.color_pair(self.COLORS['highlight']))
            self.stdscr.hline(self.height-2, 0, ' ', self.width)
            self.safe_addstr(self.height-2, 1, prompt[:self.width-2])
            self.stdscr.attroff(curses.color_pair(self.COLORS['highlight']))
        except Exception as e:
            self.logger.error(f"Error drawing filter prompt: {e}")
        
    def draw_list_view(self):
        """Draw the main service list view."""
        try:
            # Get combined services list
            combined_services = self.current_manager.get_combined_services()
            self.logger.debug(f"Drawing list view with {len(combined_services)} combined services")
    
            # Filter if needed
            if self.filter_input:
                filter_text = self.filter_input.lower()
                combined_services = [
                    (server_id, service) for server_id, service in combined_services
                    if filter_text in service.lower() or filter_text in server_id.lower()
                ]
    
            # Calculate visible rows
            visible_rows = self.height - 2  # Header and status bar
            
            # Adjust scroll offset if needed
            if self.current_row >= len(combined_services):
                self.current_row = max(0, len(combined_services) - 1)
                
            if len(combined_services) > 0:
                if self.current_row >= self.scroll_offset + visible_rows:
                    self.scroll_offset = self.current_row - visible_rows + 1
                elif self.current_row < self.scroll_offset:
                    self.scroll_offset = self.current_row
            
            # Clear the content area
            self._clear_content_area()
                
            # Draw "No services found" if list is empty
            if not combined_services:
                self.safe_addstr(1, 1, "No services found across all configured servers.")
                self.safe_addstr(2, 1, "Try adding a server in the Hosts menu (press H).")
                return
                
            # Draw each service row
            for i, (server_id, service) in enumerate(combined_services[self.scroll_offset:self.scroll_offset+visible_rows], 0):
                self._draw_service_row(i, server_id, service)
        except Exception as e:
            self.logger.error(f"Error drawing list view: {e}")
            self.safe_addstr(1, 1, f"Error drawing service list: {e}")

    def _draw_service_row(self, i, server_id, service):
        """Draw a single service row in the list view."""
        try:
            row = i + 1  # +1 for header
            
            # Get status for this service
            status = self.current_manager.get_service_status(server_id, service)
            
            # Metadata values
            metadata = status.get('metadata', {})
            hostname = metadata.get('Hostname', '-')
            vm_hostname = metadata.get('VM_hostname', '-')
            ip_addr = metadata.get('IP', '-')
            project = metadata.get('ProjectName', '-')
            vm_id = metadata.get('VM_id', '-')
            
            # Resource data
            resources = status.get('resources', {})
            pid = resources.get('pid', '-')
            memory = resources.get('memory', {})
            mem_usage = memory.get('current', '-') if memory else '-'
            cpu_usage = resources.get('cpu', '-')
            
            # Status info
            is_running = status.get('running', False)
            is_enabled = status.get('enabled', False)
            
            # Uptime calculation
            uptime = "-"
            if is_running and 'start_time' in resources:
                start_time = resources.get('start_time', 0)
                uptime_secs = time.time() - start_time
                if uptime_secs < 60:
                    uptime = f"{int(uptime_secs)}s"
                elif uptime_secs < 3600:
                    uptime = f"{int(uptime_secs/60)}m"
                elif uptime_secs < 86400:
                    uptime = f"{int(uptime_secs/3600)}h"
                else:
                    uptime = f"{int(uptime_secs/86400)}d"
            
            # VM display format
            vm_display = f"{vm_hostname}/{vm_id}" if vm_hostname != '-' or vm_id != '-' else '-/-'
            
            # Highlighter for current row
            if i + self.scroll_offset == self.current_row:
                attr = curses.color_pair(self.COLORS['selected'])
            else:
                attr = curses.color_pair(self.COLORS['normal'])
                
            # Draw each column
            self.stdscr.attron(attr)
            
            # Position for each column (must match header positions)
            pos = 0
            
            # Service name (truncated if needed)
            name_width = 25
            service_display = f"{service} ({server_id})"
            if len(service_display) > name_width:
                service_display = service_display[:name_width-3] + "..."
            self.stdscr.addstr(row, pos, service_display.ljust(name_width))

            pos += name_width + 1
            
            # Host
            host_width = 20
            self.safe_addstr(row, pos, hostname[:host_width].ljust(host_width))
            pos += host_width + 1
            
            # VM
            vm_width = 20
            self.safe_addstr(row, pos, vm_display[:vm_width].ljust(vm_width))
            pos += vm_width + 1
            
            # IP
            ip_width = 15
            self.safe_addstr(row, pos, ip_addr[:ip_width].ljust(ip_width))
            pos += ip_width + 1
            
            # Project
            project_width = 15
            self.safe_addstr(row, pos, project[:project_width].ljust(project_width))
            pos += project_width + 1
            
            # PID
            pid_width = 8
            self.safe_addstr(row, pos, str(pid)[:pid_width].ljust(pid_width))
            pos += pid_width + 1
            
            # CPU
            cpu_width = 8
            self.safe_addstr(row, pos, str(cpu_usage)[:cpu_width].ljust(cpu_width))
            pos += cpu_width + 1
            
            # Memory
            mem_width = 8
            self.safe_addstr(row, pos, str(mem_usage)[:mem_width].ljust(mem_width))
            pos += mem_width + 1
            
            # Running State
            state_width = 10
            
            # If this is the selected cell, use reverse colors
            if i + self.scroll_offset == self.current_row and self.current_col == 0:
                special_attr = curses.color_pair(self.COLORS['highlight']) | curses.A_REVERSE
                self.stdscr.attroff(attr)
                self.stdscr.attron(special_attr)
                
            state_str = "Running" if is_running else "Stopped"
            self.safe_addstr(row, pos, state_str.center(state_width))
            
            if i + self.scroll_offset == self.current_row and self.current_col == 0:
                self.stdscr.attroff(special_attr)
                self.stdscr.attron(attr)
                
            pos += state_width + 1
            
            # Boot State
            boot_width = 10
            
            # If this is the selected cell, use reverse colors
            if i + self.scroll_offset == self.current_row and self.current_col == 1:
                special_attr = curses.color_pair(self.COLORS['highlight']) | curses.A_REVERSE
                self.stdscr.attroff(attr)
                self.stdscr.attron(special_attr)
                
            boot_str = "Enabled" if is_enabled else "Disabled"
            self.safe_addstr(row, pos, boot_str.center(boot_width))
            
            if i + self.scroll_offset == self.current_row and self.current_col == 1:
                self.stdscr.attroff(special_attr)
                self.stdscr.attron(attr)
                
            pos += boot_width + 1
            
            # Uptime
            uptime_width = 8
            self.safe_addstr(row, pos, uptime.center(uptime_width))
            pos += uptime_width + 1
            
            # Logs indicator
            log_width = 8
            
            # If this is the selected log cell, highlight
            if i + self.scroll_offset == self.current_row and self.current_col == 2:
                special_attr = curses.color_pair(self.COLORS['highlight']) | curses.A_REVERSE
                self.stdscr.attroff(attr)
                self.stdscr.attron(special_attr)
                
            self.safe_addstr(row, pos, "View".center(log_width))
            
            if i + self.scroll_offset == self.current_row and self.current_col == 2:
                self.stdscr.attroff(special_attr)
                self.stdscr.attron(attr)
            
            self.stdscr.attroff(attr)
        except Exception as e:
            self.logger.error(f"Error drawing service row: {e}")

    def safe_addstr(self, y, x, text, attr=None):
        """Safely write text to the screen with boundary checking."""
        # Check if coordinates are within screen bounds
        if y >= self.height or x >= self.width:
            return False
            
        # Truncate text if it would go beyond screen width
        max_len = self.width - x - 1
        if max_len <= 0:
            return False
            
        if len(text) > max_len:
            text = text[:max_len]
        
        try:
            if attr:
                self.stdscr.attron(attr)
                
            self.stdscr.addstr(y, x, text)
            
            if attr:
                self.stdscr.attroff(attr)
                
            return True
        except curses.error:
            self.logger.debug(f"Error writing to screen at y={y}, x={x}, text={text[:20]}...")
            return False      
         
    def draw_details_view(self):
        """Draw the service details view."""
        if not self.current_service:
            return
            
        # Clear content area
        try:
            for i in range(1, self.height-1):
                self.stdscr.hline(i, 0, ' ', self.width)
        except curses.error:
            self.logger.debug("Error clearing content area")
            
        # Get service details
        details = self.current_manager.get_service_details(self.current_service)
        config = self.current_manager.client.get_service_config(self.current_service)
        resources = self.current_manager.resources.get(self.current_service, {})
        
        # Title
        row = 1
        title = f"Service Details: {self.current_service}"
        try:
            self.stdscr.attron(curses.color_pair(self.COLORS['highlight']))
            self.safe_addstr(row, 1, title[:self.width-2])
            self.stdscr.attroff(curses.color_pair(self.COLORS['highlight']))
        except curses.error:
            self.logger.debug(f"Error drawing title at row {row}")
            
        row += 2    
       
        # Basic info
        info_col1 = 20
        info_col2 = 40
        
        # Status information
        is_running = details.get('is_running', False)
        is_enabled = details.get('is_enabled', False)
        state_color = curses.color_pair(self.COLORS['status_ok'] if is_running else self.COLORS['status_error'])
        boot_color = curses.color_pair(self.COLORS['status_ok'] if is_enabled else self.COLORS['status_error'])
        
        try:
            self.safe_addstr(row, 1, "Status:")
            self.stdscr.attron(state_color)
            self.safe_addstr(row, info_col1, "Running" if is_running else "Stopped")
            self.stdscr.attroff(state_color)
        except curses.error:
            self.logger.debug(f"Error drawing Status at row {row}")
        
        try:
            self.safe_addstr(row, info_col2, "Boot Status:")
            self.stdscr.attron(boot_color)
            self.safe_addstr(row, info_col2 + info_col1, "Enabled" if is_enabled else "Disabled")
            self.stdscr.attroff(boot_color)
        except curses.error:
            self.logger.debug(f"Error drawing Boot Status at row {row}")
        row += 1
        
        # Load more detailed status info if available
        active_status = details.get('active_status', '')
        load_status = details.get('loaded_status', '')
        
        if active_status:
            try:
                self.safe_addstr(row, 1, "Active Status:")
                self.safe_addstr(row, info_col1, active_status)
            except curses.error:
                self.logger.debug(f"Error drawing Active Status at row {row}")
            row += 1
            
        if load_status:
            try:
                self.safe_addstr(row, 1, "Load Status:")
                self.safe_addstr(row, info_col1, load_status)
            except curses.error:
                self.logger.debug(f"Error drawing Load Status at row {row}")
            row += 1
            
        row += 1
        
        # Metadata section
        try:
            self.stdscr.attron(curses.A_BOLD)
            self.safe_addstr(row, 1, "METADATA")
            self.stdscr.attroff(curses.A_BOLD)
        except curses.error:
            self.logger.debug(f"Error drawing Metadata at row {row}")
        row += 1
        
        metadata = self.current_manager.metadata.get(self.current_service, {})
        if metadata:
            for key, value in metadata.items():
                if row >= self.height - 2:
                    break
                try:
                    self.safe_addstr(row, 1, f"{key}:")
                    self.safe_addstr(row, info_col1, str(value))
                except curses.error:
                    self.logger.debug(f"Error drawing {key} at row {row}")
                row += 1
        else:
            try:
                self.safe_addstr(row, 1, "No metadata available")
            except curses.error:
                    self.logger.debug(f"Error drawing 'No metadata available' at row {row}")    
            row += 1
            
        row += 1
        
        # Resource usage section
        try:
            self.stdscr.attron(curses.A_BOLD)
            self.safe_addstr(row, 1, "RESOURCE USAGE")
            self.stdscr.attroff(curses.A_BOLD)
        except curses.error:
            self.logger.debug(f"Error drawing RESOURCE USAGE at row {row}")
        row += 1
        
        pid = resources.get('pid', '-')
        try:
            self.safe_addstr(row, 1, "PID:")
            self.safe_addstr(row, info_col1, str(pid))
        except curses.error:
            self.logger.debug(f"Error drawing PID at row {row}")
        row += 1
        
        cpu = resources.get('cpu', '-')
        try:
            self.safe_addstr(row, 1, "CPU Usage:")
            self.safe_addstr(row, info_col1, str(cpu))
        except curses.error:
            self.logger.debug(f"Error drawing CPU Usage at row {row}")
        row += 1
        
        memory = resources.get('memory', {})
        if memory:
            try:
                self.safe_addstr(row, 1, "Memory Current:")
                self.safe_addstr(row, info_col1, str(memory.get('current', '-')))
            except curses.error:
                self.logger.debug(f"Error drawing Memory Current at row {row}")
            row += 1
            
            try:
                self.safe_addstr(row, 1, "Memory Peak:")
                self.safe_addstr(row, info_col1, str(memory.get('peak', '-')))
            except curses.error:
                self.logger.debug(f"Error drawing Memory Peak at row {row}")
            row += 1
        
        # Configuration section (if space available)
        if row + 2 < self.height - 2:
            row += 1
            try:
                self.stdscr.attron(curses.A_BOLD)
                self.safe_addstr(row, 1, "CONFIGURATION")
                self.stdscr.attroff(curses.A_BOLD)
            except curses.error:
                self.logger.debug(f"Error drawing CONFIGURATION at row {row}")
            row += 1
            
            unit_config = config.get('config', {})
            if unit_config:
                for section, items in unit_config.items():
                    if row >= self.height - 2:
                        break
                    try:    
                        self.stdscr.attron(curses.A_UNDERLINE)
                        self.safe_addstr(row, 1, f"[{section}]")
                        self.stdscr.attroff(curses.A_UNDERLINE)
                    except curses.error:
                        self.logger.debug(f"Error drawing [{section}] at row {row}")
                    row += 1
                    
                    for key, value in items.items():
                        if row >= self.height - 2:
                            break
                            
                        # Handle Environment which is a list
                        if key == "Environment" and isinstance(value, list):
                            for i, env_var in enumerate(value):
                                if row >= self.height - 2:
                                    break
                                try:
                                    self.safe_addstr(row, 3, f"{key}[{i}]:")
                                    self.safe_addstr(row, info_col1, str(env_var))
                                except curses.error:
                                    self.logger.debug(f"Error drawing {key}[{i}] at row {row}")
                                row += 1
                        else:
                            self.safe_addstr(row, 3, f"{key}:")
                            val_str = str(value)
                            # If value is too long, truncate it
                            if len(val_str) > self.width - info_col1 - 3:
                                val_str = val_str[:self.width - info_col1 - 6] + "..."
                            self.safe_addstr(row, info_col1, val_str)
                            row += 1
            else:
                self.safe_addstr(row, 1, "No configuration available")
        
    def draw_logs_view(self):
        """Draw the service logs view."""
        if not self.current_service:
            return
            
        # Clear content area
        for i in range(1, self.height-1):
            self.stdscr.hline(i, 0, ' ', self.width)
            
        # Get logs
        logs_data = self.current_manager.get_service_logs(self.current_service)
        
        # Title
        row = 1
        title = f"Service Logs: {self.current_service}"
        self.stdscr.attron(curses.color_pair(self.COLORS['highlight']))
        self.safe_addstr(row, 1, title[:self.width-2])
        self.stdscr.attroff(curses.color_pair(self.COLORS['highlight']))
        row += 1
        
        tool_settings = self.config.get_tool_settings()
        log_lines = tool_settings.get('log_lines', 25)
        log_time_range = tool_settings.get('log_time_range', '30 minutes ago')
        
        self.safe_addstr(row, 1, f"Last {log_lines} lines from the last {log_time_range}")
        row += 2
        
        # Display logs
        log_entries = logs_data.get('logs', [])
        for entry in log_entries:
            if row >= self.height - 1:
                break
                
            timestamp = entry.get('timestamp', '')
            message = entry.get('message', '')
            
            if timestamp:
                # If it's a parsed log with timestamp
                try:
                    # Try to fit log entry on one line with truncation if needed
                    log_line = f"[{timestamp}] {message}"
                    if len(log_line) > self.width - 3:
                        log_line = log_line[:self.width - 6] + "..."
                    self.safe_addstr(row, 1, log_line)
                except curses.error:
                    # Handle edge cases where writing to the screen might fail
                    pass
            else:
                # Raw log message
                try:
                    if len(message) > self.width - 3:
                        message = message[:self.width - 6] + "..."
                    self.safe_addstr(row, 1, message)
                except curses.error:
                    pass
                    
            row += 1
    
    def draw_settings_view(self):
        """Draw the settings configuration view."""
        self.draw_header("Settings")
        
        settings = [
            ("refresh_interval", "Auto-refresh interval (seconds)", 5, 60),
            ("log_lines", "Number of log lines to display", 10, 1000),
            ("stop_confirm", "Confirm before stopping services", None, None),
            ("restart_confirm", "Confirm before restarting services", None, None),
            ("reload_confirm", "Confirm before reloading services", None, None),
            ("enable_confirm", "Confirm before enabling services", None, None),
            ("disable_confirm", "Confirm before disabling services", None, None)
        ]
        
        # Calculate longest label for alignment
        max_label_len = max(len(label) for _, label, _, _ in settings)
        
        # Draw settings
        row = 2
        for setting_key, label, min_val, max_val in settings:
            # Get current value
            value = self.config.get_setting(setting_key)
            
            # Format display based on type
            if isinstance(value, bool):
                value_display = "Yes" if value else "No"
            else:
                value_display = str(value)
            
            # Draw setting
            try:
                self.safe_addstr(row, 2, label)
                
                # Highlight if this is the selected row
                if row - 2 == self.current_row:
                    self.stdscr.attron(curses.A_REVERSE)
                    
                self.safe_addstr(row, max_label_len + 4, value_display)
                
                if row - 2 == self.current_row:
                    self.stdscr.attroff(curses.A_REVERSE)
            except curses.error:
                pass
                
            row += 1
        
        # Draw instructions
        try:
            self.safe_addstr(row + 2, 2, "Press Enter to toggle/edit, arrow keys to navigate, Esc to return")
        except curses.error:
            pass


    def handle_list_input(self, key):
        """Handle keyboard input for the list view."""
        #services = self.current_manager.get_filtered_services()
        combined_services = self.current_manager.get_combined_services()

        # Filter if needed
        if self.filter_input:
            filter_text = self.filter_input.lower()
            combined_services = [
                (server_id, service) for server_id, service in combined_services
                if filter_text in service.lower() or filter_text in server_id.lower()
            ]
        
        if key == curses.KEY_UP:
            if self.current_row > 0:
                self.current_row -= 1
                
        elif key == curses.KEY_DOWN:
            if self.current_row < len(combined_services) - 1:
                self.current_row += 1
                
        elif key == curses.KEY_LEFT:
            if self.current_col > 0:
                self.current_col -= 1
                
        elif key == curses.KEY_RIGHT:
            if self.current_col < 2:  # 0=State, 1=Boot, 2=Logs
                self.current_col += 1
                
        elif key == self.KEY_SPACE:
            # Toggle the selected column for the current service
            if len(combined_services) == 0:
                return
                
            server_id, service = combined_services[self.current_row]
            
            # Get the appropriate controller for this server
            server_controller = self.current_manager.all_servers.get(server_id)
            if not server_controller:
                self.set_status(f"Cannot control services on {server_id}", error=True)
                return
                
            if self.current_col == 0:  # Running state
                # Get current status from the multi-server data structure
                status = self.current_manager.get_service_status(server_id, service)
                is_running = status.get('running', False)
                
                # If service is running and we're about to stop it, confirm
                if is_running and self.config.get_setting("stop_confirm", True):
                    if not self.confirm_action("stop", f"{service} on {server_id}"):
                        return  # User cancelled
                
                # Use the server-specific controller to toggle the service
                action = "stop" if is_running else "start"
                try:
                    if action == "stop":
                        result = server_controller.stop_service(service)
                    else:
                        result = server_controller.start_service(service)
                        
                    if result.get('success', False):
                        # Update status in our data structure
                        self.current_manager.all_statuses[(server_id, service)]['running'] = not is_running
                        self.set_status(f"Service {service} on {server_id} {action}ed successfully")
                    else:
                        self.set_status(f"Failed to {action} service {service} on {server_id}: {result.get('message', '')}", error=True)
                except Exception as e:
                    self.set_status(f"Error {action}ing service: {e}", error=True)
                    
            elif self.current_col == 1:  # Boot state
                # Get current status from the multi-server data structure
                status = self.current_manager.get_service_status(server_id, service)
                is_enabled = status.get('enabled', False)
                
                enable_disable = "disable" if is_enabled else "enable"
                
                # Check if we need confirmation
                if self.config.get_setting(f"{enable_disable}_confirm", False):
                    if not self.confirm_action(enable_disable, f"{service} on {server_id}"):
                        return  # User cancelled
                
                # Use the server-specific controller to toggle boot state
                try:
                    if enable_disable == "disable":
                        result = server_controller.disable_service(service)
                    else:
                        result = server_controller.enable_service(service)
                        
                    if result.get('success', False):
                        # Update status in our data structure
                        self.current_manager.all_statuses[(server_id, service)]['enabled'] = not is_enabled
                        self.set_status(f"Service {service} on {server_id} {enable_disable}d at boot")
                    else:
                        self.set_status(f"Failed to {enable_disable} service {service} on {server_id}: {result.get('message', '')}", error=True)
                except Exception as e:
                    self.set_status(f"Error changing boot state: {e}", error=True)
                    
        elif key == self.KEY_ENTER:
            # Open service details or logs based on column
            if len(combined_services) == 0:
                return
                
            server_id, service = combined_services[self.current_row]
            self.current_server = server_id
            self.current_service = service
            
            if self.current_col == 2:  # Logs column
                self.view_mode = "logs"
            else:
                self.view_mode = "details"
                
        elif key == self.KEY_r:
            # Reload data
            if self.current_manager.load_all_data():
                self.set_status("Data refreshed successfully")
            else:
                self.set_status("Failed to refresh data", error=True)
                
        elif key == self.KEY_f:
            # Enter filter mode
            self.filter_mode = True
            self.filter_input = self.current_manager.get_filter() or ""
        
        elif key == self.KEY_h:
            # Switch to hosts view
            self.view_mode = "hosts"
            self.current_row = 0


    def handle_details_input(self, key):
        """Handle keyboard input for the details view."""
        if key == ord('b') or key == self.KEY_ESC:
            self.view_mode = "list"
            
        elif key == self.KEY_l:
            self.view_mode = "logs"
            
        elif key == self.KEY_r:
            # Restart the service with confirmation
            if self.confirm_action("restart", self.current_service):
                if self.current_manager.restart_service(self.current_service):
                    self.set_status(f"Service {self.current_service} restarted successfully")
                else:
                    self.set_status(f"Failed to restart {self.current_service}", error=True)
                
        elif key == self.KEY_g:  
            # Check if service supports reload before attempting
            if not self.current_manager.service_supports_reload(self.current_service):
                # Show dialog asking if user wants to restart instead
                title = "Reload Not Supported"
                message = [
                    f"Service {self.current_service} does not support reload.",
                    "Would you like to restart it instead?"
                ]
                options = ["Restart", "Cancel"]
                
                result = self.show_dialog(title, message, options, default_option=1)
                
                if result == 0:  # User chose to restart
                    # Confirm restart
                    if self.confirm_action("restart", self.current_service):
                        if self.current_manager.restart_service(self.current_service):
                            self.set_status(f"Service {self.current_service} restarted successfully")
                        else:
                            self.set_status(f"Failed to restart {self.current_service}", error=True)
            else:
                # Service supports reload, confirm and proceed
                if self.confirm_action("reload", self.current_service):
                    if self.current_manager.reload_service(self.current_service):
                        self.set_status(f"Service {self.current_service} reloaded successfully")
                    else:
                        self.set_status(f"Failed to reload {self.current_service}", error=True)
    
    def show_reload_dialog(self):
        """Show a dialog asking if user wants to restart instead of reload.
        
        Returns:
            bool: True if user wants to restart, False otherwise
        """
        # Save current view to restore later
        self.stdscr.erase()
        
        # Create a simple dialog
        height, width = self.stdscr.getmaxyx()
        dialog_height = 6
        dialog_width = 60
        dialog_y = (height - dialog_height) // 2
        dialog_x = (width - dialog_width) // 2
        
        # Draw dialog box
        for i in range(dialog_height):
            if dialog_y + i < height:
                line = "│" + " " * (dialog_width - 2) + "│" if 0 < i < dialog_height - 1 else "┌" + "─" * (dialog_width - 2) + "┐" if i == 0 else "└" + "─" * (dialog_width - 2) + "┘"
                try:
                    self.safe_addstr(dialog_y + i, dialog_x, line)
                except curses.error:
                    pass
        
        # Add content
        try:
            self.safe_addstr(dialog_y + 1, dialog_x + 2, f"Service {self.current_service} does not support reload.")
            self.safe_addstr(dialog_y + 2, dialog_x + 2, "Would you like to restart it instead?")
            self.safe_addstr(dialog_y + 4, dialog_x + 2, "Press Y to restart, or N to cancel")
        except curses.error:
            pass
        
        self.stdscr.refresh()
        
        # Get user choice
        while True:
            try:
                key = self.stdscr.getch()
                if key in [ord('y'), ord('Y')]:
                    return True
                if key in [ord('n'), ord('N'), 27]:  # n, N or ESC
                    return False
            except Exception:
                return False

    def show_dialog(self, title, message, options=None, default_option=0):
        """Show a dialog overlay on the current screen.
        
        Args:
            title (str): Dialog title
            message (str or list): Message string or list of message lines
            options (list, optional): List of option strings. Defaults to ["OK"].
            default_option (int, optional): Index of default option. Defaults to 0.
            
        Returns:
            int: Index of selected option, or -1 if dialog was cancelled
        """
        # Convert message to list if it's a string
        if isinstance(message, str):
            message = message.split('\n')
            
        # Default options if none provided
        if options is None:
            options = ["OK"]
            
        # Calculate dialog dimensions
        message_width = max(len(line) for line in message) + 4  # 2 chars padding on each side
        option_width = sum(len(option) + 4 for option in options) + (len(options) - 1) * 2  # 4 chars padding per option + spaces between
        
        # Ensure minimum width and account for borders
        dialog_width = max(message_width, option_width, len(title) + 4) + 4
        dialog_height = len(message) + 6  # Title, padding, message, padding, options, padding
        
        # Calculate position (centered)
        dialog_y = max(0, (self.height - dialog_height) // 2)
        dialog_x = max(0, (self.width - dialog_width) // 2)
        
        # Store current screen state
        old_screen = curses.newpad(self.height, self.width)
        old_screen.overlay(self.stdscr)
        
        # Track selected option
        selected = default_option
        
        try:
            # Create dialog
            dialog = self.stdscr.derwin(dialog_height, dialog_width, dialog_y, dialog_x)

            # Fill the ENTIRE dialog with spaces
            for y in range(dialog_height):
                try:
                    dialog.hline(y, 0, ' ', dialog_width)
                except curses.error:
                    pass

            # Draw dialog box
            dialog.box()
            
            # Add title
            title_x = (dialog_width - len(title)) // 2
            try:
                dialog.attron(curses.A_BOLD)
                dialog.addstr(0, title_x, title)
                dialog.attroff(curses.A_BOLD)
            except curses.error:
                pass
            
            # Add message
            for i, line in enumerate(message):
                try:
                    dialog.addstr(i + 2, 2, line)
                except curses.error:
                    pass
            
            # Add options
            option_y = dialog_height - 2
            option_x = 2
            
            # Draw initial options
            self._draw_dialog_options(dialog, options, selected, option_y, option_x)
            
            # Make sure dialog gets focus and is visible
            dialog.keypad(True)  # Enable keypad for this window
            self.stdscr.refresh()
            dialog.refresh()
            
            # Handle input - explicitly handle each key type
            while True:
                key = dialog.getch()
                self.logger.debug(f"Dialog received key: {key}")  # Add debug logging
                
                if key == curses.KEY_LEFT or key == ord('h'):
                    if selected > 0:
                        selected -= 1
                        self._draw_dialog_options(dialog, options, selected, option_y, option_x)
                        dialog.refresh()
                        
                elif key == curses.KEY_RIGHT or key == ord('l'):
                    if selected < len(options) - 1:
                        selected += 1
                        self._draw_dialog_options(dialog, options, selected, option_y, option_x)
                        dialog.refresh()
                        
                # Add support for first letter selection
                elif options and any(chr(key).lower() == opt[0].lower() for opt in options):
                    for i, opt in enumerate(options):
                        if chr(key).lower() == opt[0].lower():
                            return i
                            
                # Support spacebar and enter as selection
                elif key in [10, 13, 32]:  # Enter or Space
                    return selected
                    
                # Support Escape and 'q' for cancel
                elif key in [27, ord('q')]:
                    return -1
        finally:
            # This will always execute, even after a return statement
            # Restore screen state
            #old_screen.overlay(self.stdscr)
            self.stdscr.erase()
            self.stdscr.refresh()

            # Explicitly refresh the full screen to ensure it's redrawn
            curses.doupdate()
    
    def _draw_dialog_options(self, dialog, options, selected, y, x_start):
        """Draw dialog options with the selected one highlighted."""
        dialog_height, dialog_width = dialog.getmaxyx()
    
        # Calculate total width needed and center the options
        total_width = sum(len(option) + 4 for option in options) + (len(options) - 1) * 2
        x = x_start

        if total_width < dialog_width - 4:
            x = (dialog_width - total_width) // 2
        
        for i, option in enumerate(options):
            # Calculate padding
            padding = 2
            option_width = len(option) + padding * 2
            
            # Set attributes based on selection
            if i == selected:
                attr = curses.A_REVERSE
            else:
                attr = curses.A_NORMAL
                
            # Draw option background
            try:
                for j in range(option_width):
                    if x + j < dialog_width - 1:  # Avoid writing beyond window edge
                        dialog.addch(y, x + j, ' ', attr)
            except curses.error:
                pass
                
            # Draw option text
            try:
                if x + padding < dialog_width - 1:
                    dialog.addstr(y, x + padding, option[:dialog_width - x - padding - 1], attr)
            except curses.error:
                pass
                    
            x += option_width + 2  # Space between options
            if x >= dialog_width - 1:
                break  # Stop if we've reached the edge of the dialog
    
    def show_key_debug(self):
        """Show a debug screen that displays key codes."""
        self.stdscr.clear()
        self.safe_addstr(0, 0, "Key Debug Mode - Press ESC twice to exit")
        self.safe_addstr(2, 0, "Press any key to see its code")
        
        y = 4
        while True:
            try:
                self.stdscr.refresh()
                key = self.stdscr.getch()
                if key == 27:  # ESC
                    # Check if next key is also ESC (within a short timeout)
                    self.stdscr.timeout(500)  # Set 500ms timeout
                    next_key = self.stdscr.getch()
                    self.stdscr.timeout(-1)  # Reset to blocking
                    if next_key == 27:
                        break
                        
                if y >= self.height - 2:
                    # Scroll content up if we reach the bottom
                    self.stdscr.move(4, 0)
                    self.stdscr.deleteln()
                    y = self.height - 3
                    
                self.safe_addstr(y, 0, f"Key code: {key}, Char: {chr(key) if 32 <= key <= 126 else 'N/A'}")
                y += 1
            except curses.error:
                pass
            except ValueError:
                self.safe_addstr(y, 0, f"Key code: {key}, Char: <non-printable>")
                y += 1
        
        self.stdscr.clear()
        self.stdscr.refresh()



    def confirm_action(self, action, service):
        """Show a confirmation dialog for a potentially disruptive action.
        
        Args:
            action (str): The action to confirm ("stop", "restart", "reload")
            service (str): The service name
            
        Returns:
            bool: True if confirmed, False otherwise
        """
        # Check if confirmation is required for this action
        setting_key = f"{action.lower()}_confirm"
        if not self.config.get_setting(setting_key, True):
            return True  # Skip confirmation if not required
        
        title = f"Confirm {action.title()}"
        message = [
            f"Are you sure you want to {action} the service:",
            f"{service}",
            "",
            "This action may disrupt service availability."
        ]
        options = ["Yes", "No"]
        
        result = self.show_dialog(title, message, options, default_option=1)  # Default to "No" for safety
        return result == 0  # Return True if "Yes" was selected

    def handle_logs_input(self, key):
        """Handle keyboard input for the logs view."""
        if key == ord('b') or key == ord('B') or key == self.KEY_ESC:
            # Switch back to details view
            self.view_mode = "details"
            # Reset any state that might cause issues
            self.scroll_offset = 0
            
        elif key == ord('q') or key == ord('Q'):
            # Quit application
            self.should_exit = True  # Add this flag to your class and check it in main_loop
    
    def handle_filter_input(self, key):
        """Handle keyboard input for the filter prompt."""
        if key == self.KEY_ESC:
            # Cancel filtering
            self.filter_mode = False
            
        elif key == self.KEY_ENTER:
            # Apply filter
            self.current_manager.set_filter(self.filter_input)
            self.filter_mode = False
            self.set_status(f"Filter applied: '{self.filter_input}'")
            
        elif key == curses.KEY_BACKSPACE or key == 127:
            # Backspace
            self.filter_input = self.filter_input[:-1]
            
        elif 32 <= key <= 126:  # Printable ASCII
            # Add character to filter
            self.filter_input += chr(key)
    
    def main_loop(self, stdscr):
        """Main application loop."""
        self.stdscr = stdscr
        self.should_exit = False
        
        # Terminal setup
        curses.curs_set(0)  # Hide cursor
        self.setup_colors()
        stdscr.timeout(100)  # Non-blocking input with 100ms timeout
        
        # Start background refresh - don't fail if initial data load fails
        try:
            if not self.current_manager.load_all_data():
                self.set_status("Failed to load initial data", error=True)
        except Exception as e:
            self.logger.error(f"Error loading initial data: {e}")
            self.set_status(f"Error loading data: {str(e)}", error=True)
        
        self.current_manager.start_refresh_thread()
        last_height, last_width = self.height, self.width
        
        try:
            while not self.should_exit:
                try:
                    # Update terminal dimensions
                    self.height, self.width = stdscr.getmaxyx()
                    
                    # Check if terminal was resized
                    if self.height != last_height or self.width != last_width:
                        # Handle resize - redraw everything
                        stdscr.clear()
                        last_height, last_width = self.height, self.width
                        self.logger.debug(f"Terminal resized to {self.width}x{self.height}")

                    # Draw the appropriate view
                    self._draw_current_view()
                    
                    # Get user input
                    key = stdscr.getch()
                    
                    # Global keys
                    if key == self.KEY_q:
                        break
                        
                    # Handle input based on current mode
                    self._handle_input(key)
                    
                    # Refresh screen
                    stdscr.refresh()
                    
                except curses.error as e:
                    # Recover from curses errors
                    self.logger.error(f"Curses error: {e}")
                    stdscr.clear()
                    self.safe_addstr(0, 0, "Terminal error occurred. Press any key to continue.")
                    stdscr.refresh()
                    stdscr.getch()  # Wait for keypress
                    stdscr.clear()
                
                except Exception as e:
                    # Handle other exceptions
                    self.logger.exception(f"Unexpected error: {e}")
                    stdscr.clear()
                    self.safe_addstr(0, 0, f"Error: {str(e)}")
                    self.safe_addstr(1, 0, "Press any key to continue...")
                    stdscr.refresh()
                    stdscr.getch()  # Wait for keypress
                    stdscr.clear()
        finally:
            # Clean up on exit - ensure terminal is cleaned up
            self.current_manager.stop_refresh_thread()
            try:
                curses.endwin()
            except Exception:
                pass

    def _draw_current_view(self):
        """Draw the appropriate view based on current mode."""
        # First clear the screen to prevent artifacts
        self.stdscr.clear()
        
        if self.view_mode == "list":
            self.draw_header()
            self.draw_list_view()
        elif self.view_mode == "details":
            self.draw_details_view()
        elif self.view_mode == "logs":
            self.draw_logs_view()
        elif self.view_mode == "hosts":
            self.draw_hosts_view()
        
        # Draw status bar (unless in filter mode)
        if not self.filter_mode:
            self.draw_status_bar()
        else:
            self.draw_filter_prompt()

    def _handle_input(self, key):
        """Handle input based on current mode."""
        try:
            if self.filter_mode:
                self.handle_filter_input(key)
            elif self.view_mode == "list":
                self.handle_list_input(key)
            elif self.view_mode == "details":
                self.handle_details_input(key)
            elif self.view_mode == "logs":
                self.handle_logs_input(key)
            elif self.view_mode == "hosts":
                self.handle_hosts_input(key)
        except Exception as e:
            # Log and show error
            self.logger.error(f"Error handling input: {e}", exc_info=True)
            self.set_status(f"Error: {str(e)}", error=True)

