import logging
import os
from pathlib import Path
from datetime import datetime

class AppLogger:
    """Centralized logging system for the Faceless Generator app."""
    
    def __init__(self, log_name="faceless_generator"):
        # Create logs directory in user's AppData (Windows) or home (Unix)
        if os.name == 'nt':
            log_dir = Path(os.environ.get('APPDATA')) / 'FacelessGenerator' / 'logs'
        else:
            log_dir = Path.home() / '.faceless_generator' / 'logs'
        
        log_dir.mkdir(parents=True, exist_ok=True)
        
        # Create log file with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = log_dir / f"{log_name}_{timestamp}.log"
        
        # Configure logger
        self.logger = logging.getLogger(log_name)
        self.logger.setLevel(logging.DEBUG)
        
        # Prevent duplicate handlers
        if not self.logger.handlers:
            # File handler (detailed)
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_handler.setLevel(logging.DEBUG)
            file_formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            file_handler.setFormatter(file_formatter)
            
            # Console handler (less verbose)
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            console_formatter = logging.Formatter('%(levelname)s: %(message)s')
            console_handler.setFormatter(console_formatter)
            
            self.logger.addHandler(file_handler)
            self.logger.addHandler(console_handler)
        
        self.log_file_path = log_file
        self.logger.info(f"Logger initialized. Log file: {log_file}")
    
    def debug(self, msg):
        self.logger.debug(msg)
    
    def info(self, msg):
        self.logger.info(msg)
    
    def warning(self, msg):
        self.logger.warning(msg)
    
    def error(self, msg):
        self.logger.error(msg)
    
    def critical(self, msg):
        self.logger.critical(msg)
    
    def exception(self, msg):
        """Log exception with traceback"""
        self.logger.exception(msg)
    
    def get_log_path(self):
        """Returns the path to the current log file"""
        return str(self.log_file_path)
