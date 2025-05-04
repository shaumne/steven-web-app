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
        # Bazı durumlarda fiyat formatları arasında büyük fark olabilir
        # Örneğin: BATS:GNE için TV'de 15.40, IG'de 1540.0 olabilir
        
        if ig_price is not None and ig_price > 0 and tv_price > 0:
            # Önce doğrudan oran kontrolü yapalım
            price_ratio = ig_price / tv_price
            
            # Eğer oran çok büyükse (örn: 50x veya daha fazla), direkt çarpanı kullan
            if price_ratio >= 50 and price_ratio <= 150:
                # Muhtemelen 100x fark var (örn: 15.40 -> 1540.0)
                normalized = float(tv_price) * 100.0
                logger.info(f"High price ratio detected: {price_ratio:.1f}x. Applying 100x multiplier. {tv_price} -> {normalized}")
                return normalized
            
            # Standart basamak farkı kontrolü
            ig_digits = len(str(int(ig_price)))
            tv_digits = len(str(int(tv_price)))
            
            # 3 veya daha fazla basamak farkı varsa, bu muhtemelen bir coin
            digit_diff = ig_digits - tv_digits
            
            if digit_diff >= 2:
                # IG fiyatı daha fazla basamaklı - çarparak normalize et
                normalized = float(tv_price) * (10 ** digit_diff)
                logger.info(f"Price normalization: TV={tv_price} ({tv_digits} digits) -> IG={ig_price} ({ig_digits} digits), multiplier=1e{digit_diff}, result={normalized}")
                return normalized
            elif digit_diff <= -2:
                # TradingView fiyatı daha fazla basamaklı - bölerek normalize et
                normalized = float(tv_price) / (10 ** abs(digit_diff))
                logger.info(f"Price normalization: TV={tv_price} ({tv_digits} digits) -> IG={ig_price} ({ig_digits} digits), divider=1e{abs(digit_diff)}, result={normalized}")
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
            
            # Get multipliers from CSV
            atr_sl_multiple = float(ticker_row['ATR Stop Loss Multiple'].values[0]) / 100.0  # CSV'deki değer % olarak
            atr_tp_multiple = float(ticker_row['ATR Profit Multiple'].values[0]) / 100.0    # CSV'deki değer % olarak
            
            # Get max position size
            max_position_size_gbp = float(ticker_row['Postion Size Max GBP'].values[0])
            
            # CSV'den Opening Price Multiple değerini al
            opening_price_multiple = float(ticker_row['Opening Price Multiple'].values[0]) / 100.0  # CSV'deki değer % olarak (96-104 arası)
            
            # Her zaman orijinal fiyatı sakla
            original_price = opening_price
            
            # Fiyat seviyesi hesaplama:
            # Direction DOWN (BUY) için fiyatı çarpana BÖL (96-100 arası değerler için artırma, 100 için aynı, 100-104 arası için azaltma)
            # Direction UP (SELL) için fiyatı çarpanla ÇARP (96-100 arası değerler için azaltma, 100 için aynı, 100-104 arası için artırma)
            
            if direction == "DOWN":  # BUY sinyali
                price_level = original_price / opening_price_multiple
                logger.info(f"Calculated BUY price level for DOWN direction: {price_level} (alert price {original_price} / {opening_price_multiple})")
            else:  # "UP" - SELL sinyali
                price_level = original_price * opening_price_multiple
                logger.info(f"Calculated SELL price level for UP direction: {price_level} (alert price {original_price} * {opening_price_multiple})")
            
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
            
            # CSV'den gelen çarpanlarla Stop Loss ve Take Profit hesapla
            # IG API her zaman positif mesafe değerleri bekler
            stop_distance = abs(atr_sl * atr_sl_multiple)
            limit_distance = abs(atr_tp * atr_tp_multiple)
            
            # Log hesaplanan değerleri
            logger.info(f"Raw stop_distance before normalization: {stop_distance} (ATR {atr_sl} * {atr_sl_multiple})")
            logger.info(f"Raw limit_distance before normalization: {limit_distance} (ATR {atr_tp} * {atr_tp_multiple})")
            
            # IG API'nin BUY ve SELL için mesafeleri nasıl kullanacağı:
            # BUY: stop_level = level - stop_distance, limit_level = level + limit_distance
            # SELL: stop_level = level + stop_distance, limit_level = level - limit_distance
            # Bu yüzden distance değerlerini her zaman pozitif göndermeliyiz
            
            # Stop ve limit mesafelerinin makul sınırlar içinde olmasını sağla
            # Maximum değerleri kontrol et - çok büyük değerler IG tarafından reddedilebilir
            MAX_STOP_PERCENT = 0.15   # Fiyatın maksimum %15'i
            MAX_LIMIT_PERCENT = 0.20  # Fiyatın maksimum %20'si
            
            max_stop_distance = price_level * MAX_STOP_PERCENT
            max_limit_distance = price_level * MAX_LIMIT_PERCENT
            
            if stop_distance > max_stop_distance:
                logger.warning(f"Stop distance {stop_distance} is too large (>{max_stop_distance}). Limiting to {max_stop_distance}")
                stop_distance = max_stop_distance
                
            if limit_distance > max_limit_distance:
                logger.warning(f"Limit distance {limit_distance} is too large (>{max_limit_distance}). Limiting to {max_limit_distance}")
                limit_distance = max_limit_distance
            
            # Eğer ig_price mevcutsa, stop ve limit mesafelerini de normalize et
            if ig_price is not None:
                # IG fiyatı ve TV fiyatı formatı arasında fark varsa ölçeklendirme faktörünü hesapla
                price_format_multiplier = 1.0
                
                if ig_price > 0 and price_level > 0:
                    # Ondalık basamak farkını bul
                    ig_digits = len(str(int(ig_price)))
                    tv_digits = len(str(int(price_level)))
                    digit_diff = ig_digits - tv_digits
                    
                    if abs(digit_diff) >= 2:
                        # Format farkı var - ölçeklendirme faktörünü belirle
                        price_format_multiplier = 10 ** digit_diff
                        logger.info(f"Price format multiplier: {price_format_multiplier} (based on {ig_digits}-{tv_digits}={digit_diff} digits)")
                
                # Mesafeleri ölçeklendir
                normalized_stop = stop_distance * price_format_multiplier
                normalized_limit = limit_distance * price_format_multiplier
                
                logger.info(f"Normalized stop_distance: {normalized_stop} (raw: {stop_distance} * {price_format_multiplier})")
                logger.info(f"Normalized limit_distance: {normalized_limit} (raw: {limit_distance} * {price_format_multiplier})")
                
                stop_distance = normalized_stop
                limit_distance = normalized_limit
            
            # Stop ve limit mesafesi minimum değer kontrolü
            MIN_DISTANCE = 0.001 * price_level  # Fiyatın en az %0.1'i
            if stop_distance < MIN_DISTANCE:
                logger.warning(f"Stop distance {stop_distance} is too small. Setting to minimum {MIN_DISTANCE}")
                stop_distance = MIN_DISTANCE
                
            if limit_distance < MIN_DISTANCE:
                logger.warning(f"Limit distance {limit_distance} is too small. Setting to minimum {MIN_DISTANCE}")
                limit_distance = MIN_DISTANCE
            
            # Calculate position size based on price_level (not original_price)
            # Pozisyon büyüklüğü: max_position_size_gbp / entry_price
            position_size_raw = max_position_size_gbp / entry_price
            logger.info(f"Raw position size calculation: {max_position_size_gbp} GBP / {entry_price} = {position_size_raw}")
            
            # IG Markets için doğru pozisyon boyutu formatı - sadece 1 ondalık basamak
            position_size = round(position_size_raw, 2)  # İki ondalık basamak kullan (eskiden 1 idi)
            
            # Serco örneğindeki sorunu çözmek için özel durum kontrolü
            # entry_price = 176.851, position_size_raw = 56.54, position_size = 56.5
            # eğer hesaplanan değer çok büyük görünüyorsa (muhtemelen fiyat formatında sorun var)
            if entry_price < 200 and position_size > 10:
                logger.info(f"Position size seems large ({position_size}) for price {entry_price}, keeping as is")
            # Eğer yüksek fiyatlı hisse ise ve hesaplanan değer de büyükse 100'e böl
            elif entry_price > 800 and position_size > 10:
                position_size = round(position_size / 100, 2)  # İki ondalık basamak kullan (eskiden 1 idi)
                logger.warning(f"Adjusting high position size for high price: {position_size}")
            
            # Log all parameters for easier debugging
            logger.info(f"Trade parameters for {ticker}:")
            logger.info(f"Original TV Price: {original_price}, Calculated Price Level: {price_level}")
            logger.info(f"Entry Price (normalized): {entry_price}")
            logger.info(f"Direction: {direction}, Trade Direction: {trade_direction}")
            logger.info(f"Raw Position Size Calc: {position_size_raw}, Final Position Size: {position_size}")
            logger.info(f"ATR SL Period: {atr_sl_period}, Multiple: {atr_sl_multiple}")
            logger.info(f"ATR TP Period: {atr_tp_period}, Multiple: {atr_tp_multiple}")
            logger.info(f"ATR Values - Stop: {atr_sl}, Take Profit: {atr_tp}")
            logger.info(f"Raw Stop Distance: {stop_distance}, Raw Limit Distance: {limit_distance}")
            
            # Return the trade parameters
            return {
                'ticker': ticker,
                'direction': trade_direction,
                'original_price': round(original_price, 4),  # TradingView'dan gelen orijinal fiyat
                'price_level': round(price_level, 4),        # Hesaplanan gerçek fiyat seviyesi (DOWN için %98)
                'entry_price': round(entry_price, 4),        # Normalize edilmiş fiyat
                'stop_distance': round(stop_distance, 2),    # 2 ondalık basamak için yuvarlanmış (eskiden 1 idi)
                'limit_distance': round(limit_distance, 2),  # 2 ondalık basamak için yuvarlanmış (eskiden 1 idi)
                'position_size': round(position_size, 2),    # Tutarlı olması için burayı da round içine aldım
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