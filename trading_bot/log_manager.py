"""
Log manager module for the trading bot
"""
import os
import logging
from logging.handlers import TimedRotatingFileHandler
from datetime import datetime, timedelta
import glob

class LogManager:
    def __init__(self, log_dir='logs', max_days=30):
        """
        Initialize log manager
        
        Args:
            log_dir (str): Directory to store log files
            max_days (int): Maximum number of days to keep log files
        """
        self.log_dir = log_dir
        self.max_days = max_days
        
        # Create logs directory if it doesn't exist
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        # Set up the logger
        self.setup_logger()
        
        # Clean old logs on startup
        self.clean_old_logs()
    
    def setup_logger(self):
        """Configure the logger with daily rotation"""
        logger = logging.getLogger()
        logger.setLevel(logging.INFO)
        
        # Remove any existing handlers
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
        
        # Create log file path
        log_file = os.path.join(self.log_dir, 'trading_bot.log')
        
        # Create timed rotating file handler
        file_handler = TimedRotatingFileHandler(
            log_file,
            when='midnight',
            interval=1,
            backupCount=self.max_days,
            encoding='utf-8'
        )
        
        # Set log format
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        
        # Add handler to logger
        logger.addHandler(file_handler)
        
        # Add console handler for development
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    
    def clean_old_logs(self):
        """Remove log files older than max_days"""
        try:
            # Calculate cutoff date
            cutoff_date = datetime.now() - timedelta(days=self.max_days)
            
            # Get all log files
            log_pattern = os.path.join(self.log_dir, 'trading_bot.log.*')
            log_files = glob.glob(log_pattern)
            
            for log_file in log_files:
                try:
                    # Get file modification time
                    file_date = datetime.fromtimestamp(os.path.getmtime(log_file))
                    
                    # Remove if older than cutoff date
                    if file_date < cutoff_date:
                        os.remove(log_file)
                        logging.info(f"Removed old log file: {log_file}")
                except Exception as e:
                    logging.error(f"Error processing log file {log_file}: {e}")
        
        except Exception as e:
            logging.error(f"Error cleaning old logs: {e}")
    
    def get_log_files(self):
        """Get list of all log files"""
        try:
            log_pattern = os.path.join(self.log_dir, 'trading_bot.log*')
            log_files = glob.glob(log_pattern)
            
            # Sort files by modification time (newest first)
            log_files.sort(key=os.path.getmtime, reverse=True)
            
            return [os.path.basename(f) for f in log_files]
        except Exception as e:
            logging.error(f"Error getting log files: {e}")
            return [] 