#!/usr/bin/env python3
"""
ShellManager - Local Shell Advanced Service Monitor and Controller
===================================================================

A condensed terminal interface for monitoring and controlling system services.
"""
import sys
import curses
import os
from .config import ShellConfig
from .terminal import Terminal
from .logging import setup_logging
from .setup_helper import create_default_config

def main():
    """Main entry point for the Shell Manager tool."""
    # Ensure config file exists
    config_file = None
    config_from_env = os.environ.get("RESOURCE_MANAGER_CONFIG_FILE")
    
    if config_from_env:
        config_file = config_from_env
    else:
        # Create default config if needed
        config_file = create_default_config()
    
    # Load configuration
    config = ShellConfig(config_file)
    
    # Setup logging
    logger = setup_logging(config)
    
    try:
        # Log startup information
        logger.info("Starting Shell Manager")
        logger.debug(f"Using configuration from: {config.client_config.config_file}")
        logger.debug(f"Active host: {config.get_current_host_id()}")
        
        # Initialize terminal with configuration and logger
        terminal = Terminal(config, logger)
        
        # Start the curses interface with proper error handling
        try:
            curses.wrapper(terminal.main_loop)
        except KeyboardInterrupt:
            logger.info("Shell Manager terminated by user (Ctrl+C)")
        except Exception as e:
            # Make sure we restore terminal state
            try:
                curses.endwin()
            except Exception:
                pass
            logger.exception(f"Terminal error: {e}")
            print(f"Terminal error: {e}", file=sys.stderr)
            return 1
            
    except KeyboardInterrupt:
        logger.info("Shell Manager terminated by user")
        # Make sure to reset terminal
        try:
            curses.endwin()
        except Exception:
            pass
    except Exception as e:
        logger.exception(f"Unhandled exception: {e}")
        print(f"Error: {e}", file=sys.stderr)
        # Make sure to reset terminal
        try:
            curses.endwin()
        except Exception:
            pass
        return 1
        
    return 0

if __name__ == "__main__":
    sys.exit(main())