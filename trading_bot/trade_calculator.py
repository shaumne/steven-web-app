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

    def get_significant_digits(self, price):
        """
        Sayının anlamlı basamak sayısını bul (noktadan önceki)
        Örn: 120.00 -> 3 basamak
             0.567 -> 0 basamak
             1234.567 -> 4 basamak
        """
        # String'e çevir
        price_str = str(float(price))
        
        # Noktadan önceki kısmı al
        before_decimal = price_str.split('.')[0]
        
        # Başındaki sıfırları kaldır
        before_decimal = before_decimal.lstrip('0')
        
        # Boşsa (örn: 0.567 için) 0 döndür
        return len(before_decimal) if before_decimal else 0

    def normalize_price(self, tv_price, ig_price):
        """
        TradingView fiyatını IG formatına çevir
        """
        # Fiyat formatını düzeltme kontrolü
        # Bazı coinlerde IG fiyatı 12430.0 iken TradingView'den 124.3 gibi gelir
        # Bu durumu tespit et ve ölçeklendir
        if ig_price is not None and ig_price > 0 and tv_price > 0:
            ig_digits = len(str(int(ig_price)))
            tv_digits = len(str(int(tv_price)))
            
            # 3 veya daha fazla basamak farkı varsa, bu muhtemelen bir coin
            digit_diff = ig_digits - tv_digits
            
            if digit_diff >= 2:
                # IG fiyatı daha fazla basamaklı - çarparak normalize et
                normalized = float(tv_price) * (10 ** digit_diff)
                logger.info(f"Price normalization for crypto/coin: TV={tv_price} ({tv_digits} digits) -> IG={ig_price} ({ig_digits} digits), multiplier=1e{digit_diff}, result={normalized}")
                return normalized
            elif digit_diff <= -2:
                # TradingView fiyatı daha fazla basamaklı - bölerek normalize et
                normalized = float(tv_price) / (10 ** abs(digit_diff))
                logger.info(f"Price normalization for crypto/coin: TV={tv_price} ({tv_digits} digits) -> IG={ig_price} ({ig_digits} digits), divider=1e{abs(digit_diff)}, result={normalized}")
                return normalized
            else:
                # Basamak farkı az - normal hesaplama yap
                tv_digits = self.get_significant_digits(tv_price)
                ig_digits = self.get_significant_digits(ig_price)
                
                # Basamak farkını bul
                digit_diff = ig_digits - tv_digits
                
                if digit_diff > 0:
                    # IG fiyatı daha fazla basamaklı
                    normalized = float(tv_price) * (10 ** digit_diff)
                    logger.info(f"Price normalization: TV={tv_price} ({tv_digits} digits) -> IG={ig_price} ({ig_digits} digits), multiplier=1e{digit_diff}, result={normalized}")
                    return normalized
                else:
                    # Aynı basamak sayısı veya IG daha az basamaklı (nadir durum)
                    logger.info(f"No normalization needed: TV={tv_price} ({tv_digits} digits), IG={ig_price} ({ig_digits} digits)")
                    return float(tv_price)
        else:
            # IG fiyatı yoksa TV fiyatını aynen döndür
            logger.info(f"No normalization possible without IG price. Using TV price: {tv_price}")
            return float(tv_price)
    
    def calculate_trade_parameters(self, ticker, direction, opening_price, atr_values, ig_price=None):
        """
        Calculate the trade parameters for a trade
        
        Args:
            ticker (str): The ticker symbol
            direction (str): 'UP' or 'DOWN' from the alert
            opening_price (float): Opening price from the alert
            atr_values (list): List of ATR values from the alert
            ig_price (float, optional): Current IG price for normalization
            
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
            
            # Her zaman orijinal fiyatı sakla
            original_price = opening_price
            
            # DOWN DIR için fiyat seviyesi hesaplama (Fiyatı %2 düşürerek)
            if direction == "DOWN":
                # Fiyat seviyesi, orijinal fiyatın %98'i olacak
                price_level = original_price * 0.98
                logger.info(f"Calculated price level for DOWN direction: {price_level} (98% of {original_price})")
            else:
                # UP için normal fiyat
                price_level = original_price
                logger.info(f"Using original price for UP direction: {price_level}")
            
            # Normalize price if IG price is provided (API için kullanılacak)
            entry_price = price_level
            if ig_price is not None:
                entry_price = self.normalize_price(price_level, ig_price)
                logger.info(f"Normalized entry price from {price_level} to {entry_price}")
            
            # Check if atr_values has enough elements
            if len(atr_values) < max(atr_sl_period, atr_tp_period):
                logger.error(f"Not enough ATR values provided for {ticker}. Need {max(atr_sl_period, atr_tp_period)}, got {len(atr_values)}")
                # Eğer yeterli ATR değeri yoksa, varsayılan değerler kullan
                logger.warning(f"Using default ATR values due to insufficient data")
                atr_sl = 0.01 * original_price  # Fiyatın %1'i
                atr_tp = 0.02 * original_price  # Fiyatın %2'si
            else:
                # Get the relevant ATR values - ATR'leri normalize etmiyoruz
                atr_sl = atr_values[atr_sl_period - 1]  # 0-indexed list
                atr_tp = atr_values[atr_tp_period - 1]  # 0-indexed list
            
            # ATR değerlerinin sıfır olması durumunu kontrol et
            if atr_sl <= 0:
                logger.warning(f"ATR Stop Loss value is zero or negative: {atr_sl}. Using default 1% of price.")
                atr_sl = 0.01 * original_price
            
            if atr_tp <= 0:
                logger.warning(f"ATR Take Profit value is zero or negative: {atr_tp}. Using default 2% of price.")
                atr_tp = 0.02 * original_price
            
            # Calculate stop loss distance - ATR stop 3 için 336% (3.36x)
            stop_distance = atr_sl * 3.36
            
            # Calculate take profit distance - ATR profit 7 için 246% (2.46x)
            limit_distance = atr_tp * 2.46
            
            # Stop ve limit mesafesi minimum değer kontrolü
            MIN_DISTANCE = 0.001 * price_level  # Fiyatın en az %0.1'i
            if stop_distance < MIN_DISTANCE:
                logger.warning(f"Stop distance {stop_distance} is too small. Setting to minimum {MIN_DISTANCE}")
                stop_distance = MIN_DISTANCE
                
            if limit_distance < MIN_DISTANCE:
                logger.warning(f"Limit distance {limit_distance} is too small. Setting to minimum {MIN_DISTANCE}")
                limit_distance = MIN_DISTANCE
            
            # Calculate position size based on price_level (not original_price)
            # Bet size hesaplama: max_position_size_gbp / price_level
            position_size = max(0.85, round(max_position_size_gbp / price_level, 2))
            
            # Pozisyon büyüklüğünü sınırla - çok büyük emirler reddedilebilir
            MAX_SAFE_POSITION_SIZE = 40.0
            if position_size > MAX_SAFE_POSITION_SIZE:
                logger.warning(f"Position size {position_size} is too large. Limiting to {MAX_SAFE_POSITION_SIZE}")
                position_size = MAX_SAFE_POSITION_SIZE
            
            # Log all parameters for easier debugging
            logger.info(f"Trade parameters for {ticker}:")
            logger.info(f"Original TV Price: {original_price}, Calculated Price Level: {price_level}")
            logger.info(f"Entry Price (normalized): {entry_price}")
            logger.info(f"Position Size: {position_size} (calculated using price level: {price_level})")
            logger.info(f"Stop Distance: {stop_distance}")
            logger.info(f"Limit Distance: {limit_distance}")
            logger.info(f"ATR Values - Stop: {atr_sl}, Take Profit: {atr_tp}")
            
            # Return the trade parameters
            return {
                'ticker': ticker,
                'direction': trade_direction,
                'original_price': round(original_price, 4),  # TradingView'dan gelen orijinal fiyat
                'price_level': round(price_level, 4),        # Hesaplanan gerçek fiyat seviyesi (DOWN için %98)
                'entry_price': round(entry_price, 4),        # Normalize edilmiş fiyat
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