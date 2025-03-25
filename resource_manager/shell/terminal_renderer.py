# This file contains the TerminalRenderer class, which is responsible for rendering the terminal UI.
import curses
import time
from .dialog_manager import Colors


class TerminalRenderer:
    """Handles all terminal UI rendering."""
    
    def __init__(self, stdscr, logger):
        self.stdscr = stdscr
        self.logger = logger
        self.height, self.width = stdscr.getmaxyx() if stdscr else (24, 80)
    
    def update_dimensions(self, height, width):
        """Update the current screen dimensions."""
        self.height = height
        self.width = width
    
    def setup_colors(self):
        """Initialize color pairs for the UI."""
        try:
            curses.start_color()
            curses.use_default_colors()
            curses.init_pair(Colors.HEADER, curses.COLOR_BLACK, curses.COLOR_CYAN)
            curses.init_pair(Colors.STATUS_OK, curses.COLOR_GREEN, -1)
            curses.init_pair(Colors.STATUS_ERROR, curses.COLOR_RED, -1)
            curses.init_pair(Colors.HIGHLIGHT, curses.COLOR_CYAN, -1)
            curses.init_pair(Colors.NORMAL, -1, -1)
            curses.init_pair(Colors.SELECTED, curses.COLOR_BLACK, curses.COLOR_WHITE)
        except Exception as e:
            self.logger.error(f"Error setting up colors: {e}")
    
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
            
    def clear_content_area(self):
        """Clear the main content area of the screen."""
        try:
            for i in range(1, self.height-1):
                self.stdscr.move(i, 0)
                self.stdscr.clrtoeol()
        except curses.error:
            pass
    
    def draw_header(self, title=None):
        """Draw the header row with column names or a title."""
        try:
            # First, clear the entire header line
            self.stdscr.move(0, 0)
            self.stdscr.clrtoeol()

            # Apply header color
            header = curses.color_pair(Colors.HEADER)
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
            
    def draw_status_bar(self, status_message, status_time, help_text, last_refresh, refresh_interval, color=None):
        """Draw the status bar at the bottom of the screen."""
        if self.stdscr is None:
            return
            
        try:
            if color is None:
                color = curses.color_pair(Colors.NORMAL)
                
            self.stdscr.attron(color)
            self.stdscr.hline(self.height-1, 0, ' ', self.width)
            
            # Show refresh countdown
            now = time.time()
            time_since_refresh = now - last_refresh
            refresh_in = max(0, int(refresh_interval - time_since_refresh))
            refresh_text = f"Refresh in: {refresh_in}s"
            
            # Show status message if it's recent (< 5 seconds)
            if time.time() - status_time < 5 and status_message:
                self.safe_addstr(self.height-1, 1, f"{status_message[:self.width-len(refresh_text)-5]} | {refresh_text}")
            else:
                # Otherwise show contextual help text
                self.safe_addstr(self.height-1, 1, f"{help_text[:self.width-len(refresh_text)-5]} | {refresh_text}")
                
            self.stdscr.attroff(color)
        except Exception as e:
            self.logger.error(f"Error drawing status bar: {e}")
            
    def draw_filter_prompt(self, filter_input):
        """Draw the filter input prompt."""
        try:
            prompt = f"Filter: {filter_input}"
            self.stdscr.attron(curses.color_pair(Colors.HIGHLIGHT))
            self.stdscr.hline(self.height-2, 0, ' ', self.width)
            self.safe_addstr(self.height-2, 1, prompt[:self.width-2])
            self.stdscr.attroff(curses.color_pair(Colors.HIGHLIGHT))
        except Exception as e:
            self.logger.error(f"Error drawing filter prompt: {e}")
            
    def draw_service_row(self, i, server_id, service, current_row, scroll_offset, current_col, status):
        """Draw a single service row in the list view."""
        try:
            row = i + 1  # +1 for header
            
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
            if i + scroll_offset == current_row:
                attr = curses.color_pair(Colors.SELECTED)
            else:
                attr = curses.color_pair(Colors.NORMAL)
                
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
            if i + scroll_offset == current_row and current_col == 0:
                special_attr = curses.color_pair(Colors.HIGHLIGHT) | curses.A_REVERSE
                self.stdscr.attroff(attr)
                self.stdscr.attron(special_attr)
                
            state_str = "Running" if is_running else "Stopped"
            self.safe_addstr(row, pos, state_str.center(state_width))
            
            if i + scroll_offset == current_row and current_col == 0:
                self.stdscr.attroff(special_attr)
                self.stdscr.attron(attr)
                
            pos += state_width + 1
            
            # Boot State
            boot_width = 10
            
            # If this is the selected cell, use reverse colors
            if i + scroll_offset == current_row and current_col == 1:
                special_attr = curses.color_pair(Colors.HIGHLIGHT) | curses.A_REVERSE
                self.stdscr.attroff(attr)
                self.stdscr.attron(special_attr)
                
            boot_str = "Enabled" if is_enabled else "Disabled"
            self.safe_addstr(row, pos, boot_str.center(boot_width))
            
            if i + scroll_offset == current_row and current_col == 1:
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
            if i + scroll_offset == current_row and current_col == 2:
                special_attr = curses.color_pair(Colors.HIGHLIGHT) | curses.A_REVERSE
                self.stdscr.attroff(attr)
                self.stdscr.attron(special_attr)
                
            self.safe_addstr(row, pos, "View".center(log_width))
            
            if i + scroll_offset == current_row and current_col == 2:
                self.stdscr.attroff(special_attr)
                self.stdscr.attron(attr)
            
            self.stdscr.attroff(attr)
        except Exception as e:
            self.logger.error(f"Error drawing service row: {e}")
