"""
Trading Bot package for automated trading based on TradingView alerts
"""
import logging
from trading_bot.config import LOG_LEVEL, LOG_FORMAT, LOG_FILE

# Set up logging
logging.basicConfig(
    level=LOG_LEVEL,
    format=LOG_FORMAT,
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)

# Import key modules
from trading_bot.webhook_handler import WebhookHandler
from trading_bot.trade_manager import TradeManager
from trading_bot.trade_calculator import TradeCalculator
from trading_bot.ig_api import IGClient 