"""
Configuration settings for the Trading Bot
"""
import os
from dotenv import load_dotenv
import logging
import pandas as pd
from datetime import datetime, timedelta

# Load environment variables
load_dotenv()

# API Credentials
IG_USERNAME = os.getenv("IG_USERNAME")
IG_PASSWORD = os.getenv("IG_PASSWORD")
IG_API_KEY = os.getenv("IG_API_KEY")
IG_ACCOUNT_TYPE = os.getenv("IG_ACCOUNT_TYPE", "DEMO")  # DEMO or LIVE

# Trading Settings
MAX_OPEN_POSITIONS = 10
ALERT_MAX_AGE_SECONDS = 5
CSV_FILE_PATH = os.getenv("CSV_FILE_PATH", "ticker_data.csv")
TICKER_DATA_FILE = CSV_FILE_PATH  # Alias for backward compatibility

# Logging Configuration
LOG_LEVEL = logging.INFO
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
LOG_FILE = 'trading_bot.log'

# Trading hours (UK time)
TRADING_HOURS = {
    'LSE_DLY': {'start': '08:00', 'end': '16:30'},
    'BATS': {'start': '14:30', 'end': '21:00'},
    'ASX_DLY': {'start': '00:00', 'end': '06:00'},
    'TSX_DLY': {'start': '14:30', 'end': '21:00'},
    'HKEX_DLY': {'start': '01:30', 'end': '08:00'},
    'TSE_DLY': {'start': '00:00', 'end': '06:00'},
    'EURONEXT_DLY': {'start': '09:00', 'end': '17:30'},
    'VIE_DLY': {'start': '09:00', 'end': '17:30'},
    'XETR_DLY': {'start': '09:00', 'end': '17:30'},
}

# Load ticker data
def load_ticker_data():
    """Load ticker data from CSV file"""
    try:
        return pd.read_csv(CSV_FILE_PATH)
    except Exception as e:
        logging.error(f"Failed to load ticker data from {CSV_FILE_PATH}: {e}")
        return pd.DataFrame()

# Check if it's a dividend date
def is_dividend_date(ticker, ticker_data):
    """Check if today is a dividend date for the given ticker"""
    if ticker_data.empty:
        return False
    
    ticker_row = ticker_data[ticker_data['Symbol'] == ticker]
    if ticker_row.empty or pd.isna(ticker_row['Next dividend date'].values[0]) or ticker_row['Next dividend date'].values[0] == 'na':
        return False
    
    dividend_date_str = ticker_row['Next dividend date'].values[0]
    try:
        dividend_date = datetime.strptime(dividend_date_str, '%d/%m/%Y')
        today = datetime.now().date()
        return dividend_date.date() == today
    except Exception as e:
        logging.error(f"Error parsing dividend date for {ticker}: {e}")
        return False

# Get IG EPIC code for a symbol
def get_ig_epic(symbol, ticker_data):
    """Get the IG EPIC code for the given symbol"""
    if ticker_data.empty:
        return None
    
    ticker_row = ticker_data[ticker_data['Symbol'] == symbol]
    if ticker_row.empty or ticker_row['IG EPIC'].values[0] == '?':
        return None
    
    return ticker_row['IG EPIC'].values[0] 