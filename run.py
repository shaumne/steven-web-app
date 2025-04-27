"""
Runner script for the Trading Bot
"""
import os
import shutil
import logging
from dotenv import load_dotenv
import pandas as pd
from app import app
from trading_bot.config import CSV_FILE_PATH

def initialize():
    """Initialize the bot before running"""
    # Load environment variables
    load_dotenv()
    
    # Check if CSV file exists
    csv_file = os.environ.get('CSV_FILE_PATH', CSV_FILE_PATH)
    if not os.path.exists(csv_file) and os.path.exists('Version 1 ticker CSV.csv'):
        # Copy the source CSV to the configured path
        shutil.copy('Version 1 ticker CSV.csv', csv_file)
        logging.info(f"Copied 'Version 1 ticker CSV.csv' to '{csv_file}'")
    
    # Verify the CSV file
    try:
        df = pd.read_csv(csv_file)
        logging.info(f"Successfully loaded CSV file with {len(df)} tickers")
    except Exception as e:
        logging.error(f"Error loading CSV file: {e}")
        raise

if __name__ == '__main__':
    # Initialize the bot
    initialize()
    
    # Get port from environment or default to 5000
    port = int(os.environ.get('PORT', 5000))
    
    # Enable debug mode in development
    debug = os.environ.get('FLASK_ENV') == 'development'
    
    # Start the Flask server
    app.run(host='0.0.0.0', port=port, debug=debug) 