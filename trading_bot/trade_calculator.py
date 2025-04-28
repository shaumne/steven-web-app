"""
Trade calculator for computing trade parameters
"""
import logging
import pandas as pd
import numpy as np
from datetime import datetime

logger = logging.getLogger(__name__)

class TradeCalculator:
    """
    Calculator for trade parameters based on alert data and CSV configuration
    """
    
    def __init__(self, ticker_data_df):
        """
        Initialize the trade calculator
        
        Args:
            ticker_data_df (DataFrame): DataFrame containing ticker configuration data
        """
        self.ticker_data = ticker_data_df
    
    def calculate_trade_parameters(self, ticker, direction, opening_price, atr_values):
        """
        Calculate the trade parameters for a trade
        
        Args:
            ticker (str): The ticker symbol
            direction (str): 'UP' or 'DOWN' from the alert
            opening_price (float): Opening price from the alert
            atr_values (list): List of ATR values from the alert
            
        Returns:
            dict: Dictionary containing calculated trade parameters or None if failed
        """
        try:
            # Find the ticker in the configuration data
            ticker_row = self.ticker_data[self.ticker_data['Symbol'] == ticker]
            
            if ticker_row.empty:
                logger.error(f"Ticker {ticker} not found in configuration data")
                return None
            
            # Convert direction to trade direction
            trade_direction = "SELL" if direction == "UP" else "BUY"
            
            # Get ATR indices for stop loss and take profit
            atr_sl_period = int(ticker_row['ATR Stop Loss Period'].values[0])
            atr_tp_period = int(ticker_row['ATR Profit Target Period'].values[0])
            
            # Get multipliers
            atr_sl_multiple = float(ticker_row['ATR Stop Loss Multiple'].values[0])
            atr_tp_multiple = float(ticker_row['ATR Profit Multiple'].values[0])
            
            # Get max position size
            max_position_size_gbp = float(ticker_row['Postion Size Max GBP'].values[0])
            
            # Use exact price from TradingView
            entry_price = opening_price
            
            # Check if atr_values has enough elements
            if len(atr_values) < max(atr_sl_period, atr_tp_period):
                logger.error(f"Not enough ATR values provided for {ticker}")
                return None
            
            # Get the relevant ATR values
            atr_sl = atr_values[atr_sl_period - 1]  # 0-indexed list
            atr_tp = atr_values[atr_tp_period - 1]  # 0-indexed list
            
            # Calculate stop loss and take profit distances in points
            stop_distance = atr_sl * atr_sl_multiple / 100
            limit_distance = atr_tp * atr_tp_multiple / 100
            
            # Calculate position size with minimum size consideration
            # IG minimum size is usually 1.0 for most instruments
            base_size = max_position_size_gbp / entry_price
            
            # Eğer fiyat 100'den büyükse, minimum 1.0 olacak şekilde yuvarla
            if entry_price > 100:
                position_size = max(1.0, round(base_size, 1))
            else:
                # Düşük fiyatlı hisseler için daha hassas hesaplama
                position_size = round(base_size, 2)
            
            logger.info(f"Trade parameters for {ticker}: Entry Price: {entry_price}, Position Size: {position_size}")
            
            # Return the trade parameters
            return {
                'ticker': ticker,
                'direction': trade_direction,
                'entry_price': round(entry_price, 4),
                'stop_distance': round(stop_distance, 4),
                'limit_distance': round(limit_distance, 4),
                'position_size': position_size,
                'max_position_size_gbp': max_position_size_gbp
            }
            
        except Exception as e:
            logger.error(f"Error calculating trade parameters for {ticker}: {e}")
            return None
    
    def parse_alert_message(self, alert_message):
        """
        Parse an alert message from TradingView
        
        Args:
            alert_message (str): Alert message in the format "TICKER DIRECTION OPENING_PRICE ATR1 ATR2 ... ATR10"
            
        Returns:
            tuple: (ticker, direction, opening_price, atr_values) or None if parsing failed
        """
        try:
            parts = alert_message.strip().split()
            
            if len(parts) < 13:  # ticker + direction + opening_price + 10 ATR values
                logger.error(f"Invalid alert message format: {alert_message}")
                return None
            
            ticker = parts[0]
            direction = parts[1]
            opening_price = float(parts[2])
            atr_values = [float(parts[i]) for i in range(3, 13)]
            
            return ticker, direction, opening_price, atr_values
            
        except Exception as e:
            logger.error(f"Error parsing alert message: {e}")
            return None 