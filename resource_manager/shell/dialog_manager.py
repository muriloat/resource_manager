import curses
import logging

# Constants for key codes
class KeyCode:
    ESC = 27
    ENTER = 10
    SPACE = 32
    BACKSPACE = 127
    UP = curses.KEY_UP
    DOWN = curses.KEY_DOWN
    LEFT = curses.KEY_LEFT
    RIGHT = curses.KEY_RIGHT
    HOME = curses.KEY_HOME
    END = curses.KEY_END
    DELETE = curses.KEY_DC
    # Letter keys
    Q = ord('q')
    R = ord('r')
    F = ord('f')
    G = ord('g')
    H = ord('h')
    L = ord('l')
    B = ord('b')
    A = ord('a')
    D = ord('d')
    # Symbol keys
    SLASH = 47

# View mode constants
class ViewMode:
    LIST = "list"
    DETAILS = "details"
    LOGS = "logs"
    HOSTS = "hosts"
    SETTINGS = "settings"

# Color definitions
class Colors:
    HEADER = 1
    STATUS_OK = 2
    STATUS_ERROR = 3
    HIGHLIGHT = 4
    NORMAL = 5
    SELECTED = 6


class DialogManager:
    """Handles displaying dialogs and getting user input."""
    
    def __init__(self, stdscr, logger):
        self.stdscr = stdscr
        self.logger = logger
        self.height, self.width = stdscr.getmaxyx() if stdscr else (24, 80)
        
    def update_dimensions(self, height, width):
        """Update the current screen dimensions."""
        self.height = height
        self.width = width
    
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
                
                if key in [KeyCode.ENTER]:  # Enter
                    return current_text
                    
                elif key == KeyCode.ESC:  # ESC
                    return None
                    
                elif key == KeyCode.LEFT and cursor_pos > 0:
                    cursor_pos -= 1
                    
                elif key == KeyCode.RIGHT and cursor_pos < len(current_text):
                    cursor_pos += 1
                    
                elif key == KeyCode.HOME:
                    cursor_pos = 0
                    
                elif key == KeyCode.END:
                    cursor_pos = len(current_text)
                    
                elif key in [curses.KEY_BACKSPACE, KeyCode.BACKSPACE]:  # Backspace
                    if cursor_pos > 0:
                        current_text = current_text[:cursor_pos-1] + current_text[cursor_pos:]
                        cursor_pos -= 1
                        
                elif key == KeyCode.DELETE:  # Delete key
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
                
                if key == KeyCode.LEFT or key == ord('h'):
                    if selected > 0:
                        selected -= 1
                        self._draw_dialog_options(dialog, options, selected, option_y, option_x)
                        dialog.refresh()
                        
                elif key == KeyCode.RIGHT or key == ord('l'):
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
                elif key in [KeyCode.ENTER, KeyCode.SPACE]:  # Enter or Space
                    return selected
                    
                # Support Escape and 'q' for cancel
                elif key in [KeyCode.ESC, KeyCode.Q]:
                    return -1
        finally:
            # This will always execute, even after a return statement
            # Restore screen state
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

