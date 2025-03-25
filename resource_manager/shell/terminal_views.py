from .dialog_manager import Colors
import curses

class TerminalViews:
    """Handles drawing different terminal views."""
    
    def __init__(self, renderer, logger, manager):
        self.renderer = renderer
        self.logger = logger
        self.manager = manager
    
    def draw_list_view(self, current_row, scroll_offset, current_col, filter_input):
        """Draw the main service list view."""
        try:
            # Get combined services list
            combined_services = self.manager.get_combined_services()
            self.logger.debug(f"Drawing list view with {len(combined_services)} combined services")
    
            # Filter if needed
            if filter_input:
                filter_text = filter_input.lower()
                combined_services = [
                    (server_id, service) for server_id, service in combined_services
                    if filter_text in service.lower() or filter_text in server_id.lower()
                ]
    
            # Calculate visible rows
            visible_rows = self.renderer.height - 2  # Header and status bar
                
            # Draw "No services found" if list is empty
            if not combined_services:
                self.renderer.safe_addstr(1, 1, "No services found across all configured servers.")
                self.renderer.safe_addstr(2, 1, "Try adding a server in the Hosts menu (press H).")
                return combined_services
                
            # Draw each service row
            for i, (server_id, service) in enumerate(combined_services[scroll_offset:scroll_offset+visible_rows], 0):
                status = self.manager.get_service_status(server_id, service)
                self.renderer.draw_service_row(i, server_id, service, current_row, scroll_offset, current_col, status)
                
            return combined_services
        except Exception as e:
            self.logger.error(f"Error drawing list view: {e}")
            self.renderer.safe_addstr(1, 1, f"Error drawing service list: {e}")
            return []
    
    def draw_details_view(self, current_service):
        """Draw the service details view."""
        if not current_service:
            return
            
        # Clear content area
        self.renderer.clear_content_area()
            
        # Get service details
        details = self.manager.get_service_details(current_service)
        config = self.manager.client.get_service_config(current_service)
        resources = self.manager.resources.get(current_service, {})
        
        # Title
        row = 1
        title = f"Service Details: {current_service}"
        try:
            self.renderer.stdscr.attron(curses.color_pair(Colors.HIGHLIGHT))
            self.renderer.safe_addstr(row, 1, title)
            self.renderer.stdscr.attroff(curses.color_pair(Colors.HIGHLIGHT))
        except curses.error:
            self.logger.debug(f"Error drawing title at row {row}")
            
        row += 2    
       
        # Basic info
        info_col1 = 20
        info_col2 = 40
        
        # Status information
        is_running = details.get('is_running', False)
        is_enabled = details.get('is_enabled', False)
        state_color = curses.color_pair(Colors.STATUS_OK if is_running else Colors.STATUS_ERROR)
        boot_color = curses.color_pair(Colors.STATUS_OK if is_enabled else Colors.STATUS_ERROR)
        
        try:
            self.renderer.safe_addstr(row, 1, "Status:")
            self.renderer.stdscr.attron(state_color)
            self.renderer.safe_addstr(row, info_col1, "Running" if is_running else "Stopped")
            self.renderer.stdscr.attroff(state_color)
        except curses.error:
            self.logger.debug(f"Error drawing Status at row {row}")
        
        try:
            self.renderer.safe_addstr(row, info_col2, "Boot Status:")
            self.renderer.stdscr.attron(boot_color)
            self.renderer.safe_addstr(row, info_col2 + info_col1, "Enabled" if is_enabled else "Disabled")
            self.renderer.stdscr.attroff(boot_color)
        except curses.error:
            self.logger.debug(f"Error drawing Boot Status at row {row}")
        row += 1
        
        # Load more detailed status info if available
        active_status = details.get('active_status', '')
        load_status = details.get('loaded_status', '')
        
        if active_status:
            try:
                self.renderer.safe_addstr(row, 1, "Active Status:")
                self.renderer.safe_addstr(row, info_col1, active_status)
            except curses.error:
                self.logger.debug(f"Error drawing Active Status at row {row}")
            row += 1
            
        if load_status:
            try:
                self.renderer.safe_addstr(row, 1, "Load Status:")
                self.renderer.safe_addstr(row, info_col1, load_status)
            except curses.error:
                self.logger.debug(f"Error drawing Load Status at row {row}")
            row += 1
            
        row += 1
        
        # Metadata section
        try:
            self.renderer.stdscr.attron(curses.A_BOLD)
            self.renderer.safe_addstr(row, 1, "METADATA")
            self.renderer.stdscr.attroff(curses.A_BOLD)
        except curses.error:
            self.logger.debug(f"Error drawing Metadata at row {row}")
        row += 1
        
        metadata = self.manager.metadata.get(current_service, {})
        if metadata:
            for key, value in metadata.items():
                if row >= self.renderer.height - 2:
                    break
                try:
                    self.renderer.safe_addstr(row, 1, f"{key}:")
                    self.renderer.safe_addstr(row, info_col1, str(value))
                except curses.error:
                    self.logger.debug(f"Error drawing {key} at row {row}")
                row += 1
        else:
            try:
                self.renderer.safe_addstr(row, 1, "No metadata available")
            except curses.error:
                    self.logger.debug(f"Error drawing 'No metadata available' at row {row}")    
            row += 1
            
        row += 1
        
        # Resource usage section
        try:
            self.renderer.stdscr.attron(curses.A_BOLD)
            self.renderer.safe_addstr(row, 1, "RESOURCE USAGE")
            self.renderer.stdscr.attroff(curses.A_BOLD)
        except curses.error:
            self.logger.debug(f"Error drawing RESOURCE USAGE at row {row}")
        row += 1
        
        pid = resources.get('pid', '-')
        try:
            self.renderer.safe_addstr(row, 1, "PID:")
            self.renderer.safe_addstr(row, info_col1, str(pid))
        except curses.error:
            self.logger.debug(f"Error drawing PID at row {row}")
        row += 1
        
        cpu = resources.get('cpu', '-')
        try:
            self.renderer.safe_addstr(row, 1, "CPU Usage:")
            self.renderer.safe_addstr(row, info_col1, str(cpu))
        except curses.error:
            self.logger.debug(f"Error drawing CPU Usage at row {row}")
        row += 1
        
        memory = resources.get('memory', {})
        if memory:
            try:
                self.renderer.safe_addstr(row, 1, "Memory Current:")
                self.renderer.safe_addstr(row, info_col1, str(memory.get('current', '-')))
            except curses.error:
                self.logger.debug(f"Error drawing Memory Current at row {row}")
            row += 1
            
            try:
                self.renderer.safe_addstr(row, 1, "Memory Peak:")
                self.renderer.safe_addstr(row, info_col1, str(memory.get('peak', '-')))
            except curses.error:
                self.logger.debug(f"Error drawing Memory Peak at row {row}")
            row += 1
        
        # Configuration section (if space available)
        if row + 2 < self.renderer.height - 2:
            row += 1
            try:
                self.renderer.stdscr.attron(curses.A_BOLD)
                self.renderer.safe_addstr(row, 1, "CONFIGURATION")
                self.renderer.stdscr.attroff(curses.A_BOLD)
            except curses.error:
                self.logger.debug(f"Error drawing CONFIGURATION at row {row}")
            row += 1
            
            unit_config = config.get('config', {})
            if unit_config:
                for section, items in unit_config.items():
                    if row >= self.renderer.height - 2:
                        break
                    try:    
                        self.renderer.stdscr.attron(curses.A_UNDERLINE)
                        self.renderer.safe_addstr(row, 1, f"[{section}]")
                        self.renderer.stdscr.attroff(curses.A_UNDERLINE)
                    except curses.error:
                        self.logger.debug(f"Error drawing [{section}] at row {row}")
                    row += 1
                    
                    for key, value in items.items():
                        if row >= self.renderer.height - 2:
                            break
                            
                        # Handle Environment which is a list
                        if key == "Environment" and isinstance(value, list):
                            for i, env_var in enumerate(value):
                                if row >= self.renderer.height - 2:
                                    break
                                try:
                                    self.renderer.safe_addstr(row, 3, f"{key}[{i}]:")
                                    self.renderer.safe_addstr(row, info_col1, str(env_var))
                                except curses.error:
                                    self.logger.debug(f"Error drawing {key}[{i}] at row {row}")
                                row += 1
                        else:
                            self.renderer.safe_addstr(row, 3, f"{key}:")
                            val_str = str(value)
                            # If value is too long, truncate it
                            if len(val_str) > self.renderer.width - info_col1 - 3:
                                val_str = val_str[:self.renderer.width - info_col1 - 6] + "..."
                            self.renderer.safe_addstr(row, info_col1, val_str)
                            row += 1
            else:
                self.renderer.safe_addstr(row, 1, "No configuration available")
        
    def draw_logs_view(self, current_service):
        """Draw the service logs view."""
        if not current_service:
            return
            
        # Clear content area
        self.renderer.clear_content_area()
            
        # Get logs
        logs_data = self.manager.get_service_logs(current_service)
        
        # Title
        row = 1
        title = f"Service Logs: {current_service}"
        self.renderer.stdscr.attron(curses.color_pair(Colors.HIGHLIGHT))
        self.renderer.safe_addstr(row, 1, title[:self.renderer.width-2])
        self.renderer.stdscr.attroff(curses.color_pair(Colors.HIGHLIGHT))
        row += 1
        
        tool_settings = self.manager.config.get_tool_settings()
        log_lines = tool_settings.get('log_lines', 25)
        log_time_range = tool_settings.get('log_time_range', '30 minutes ago')
        
        self.renderer.safe_addstr(row, 1, f"Last {log_lines} lines from the last {log_time_range}")
        row += 2
        
        # Display logs
        log_entries = logs_data.get('logs', [])
        for entry in log_entries:
            if row >= self.renderer.height - 1:
                break
                
            timestamp = entry.get('timestamp', '')
            message = entry.get('message', '')
            
            if timestamp:
                # If it's a parsed log with timestamp
                try:
                    # Try to fit log entry on one line with truncation if needed
                    log_line = f"[{timestamp}] {message}"
                    if len(log_line) > self.renderer.width - 3:
                        log_line = log_line[:self.renderer.width - 6] + "..."
                    self.renderer.safe_addstr(row, 1, log_line)
                except curses.error:
                    # Handle edge cases where writing to the screen might fail
                    pass
            else:
                # Raw log message
                try:
                    if len(message) > self.renderer.width - 3:
                        message = message[:self.renderer.width - 6] + "..."
                    self.renderer.safe_addstr(row, 1, message)
                except curses.error:
                    pass
                    
            row += 1
    
    def draw_settings_view(self, current_row, config):
        """Draw the settings configuration view."""
        self.renderer.draw_header("Settings")
        
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
            value = config.get_setting(setting_key)
            
            # Format display based on type
            if isinstance(value, bool):
                value_display = "Yes" if value else "No"
            else:
                value_display = str(value)
            
            # Draw setting
            try:
                self.renderer.safe_addstr(row, 2, label)
                
                # Highlight if this is the selected row
                if row - 2 == current_row:
                    self.renderer.stdscr.attron(curses.A_REVERSE)
                    
                self.renderer.safe_addstr(row, max_label_len + 4, value_display)
                
                if row - 2 == current_row:
                    self.renderer.stdscr.attroff(curses.A_REVERSE)
            except curses.error:
                pass
                
            row += 1
        
        # Draw instructions
        try:
            self.renderer.safe_addstr(row + 2, 2, "Press Enter to toggle/edit, arrow keys to navigate, Esc to return")
        except curses.error:
            pass

    def draw_filter_prompt(self, filter_input):
        """Draw the filter input prompt."""
        self.renderer.draw_filter_prompt(filter_input)