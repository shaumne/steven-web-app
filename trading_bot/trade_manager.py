"""
Trade manager for handling trading operations
"""
import logging
import time
import os
import json
from datetime import datetime, timedelta
import pandas as pd
from trading_bot.ig_api import IGClient
from trading_bot.trade_calculator import TradeCalculator
from trading_bot.config import (
    MAX_OPEN_POSITIONS, ALERT_MAX_AGE_SECONDS, load_ticker_data, 
    is_dividend_date
)

logger = logging.getLogger(__name__)

class TradeManager:
    """
    Manager for handling trading operations
    """
    
    def __init__(self):
        """Initialize the trade manager"""
        self.ig_client = IGClient()
        self.ticker_data = load_ticker_data()
        self.trade_calculator = TradeCalculator(self.ticker_data)
        self.today_trades = {}  # To track trades made today by ticker
        
        # Load settings from settings.json
        self.load_settings()
        
        self.epic_cache = {}  # Cache for EPIC codes to avoid repeated API calls
    
    def load_settings(self):
        """Load settings from settings.json file"""
        settings_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'settings.json')
        try:
            with open(settings_path, 'r') as f:
                settings = json.load(f)
                
            # Load validation rules
            self.validation_rules = settings.get('validation', {
                'check_same_day_trades': True,
                'check_open_position_limit': True,
                'check_existing_position': True,
                'check_alert_timestamp': True,
                'check_dividend_date': True
            })
            
            # Load trading settings
            trading_settings = settings.get('trading', {})
            self.max_open_positions = trading_settings.get('max_open_positions', MAX_OPEN_POSITIONS)
            self.alert_max_age_seconds = trading_settings.get('alert_max_age_seconds', ALERT_MAX_AGE_SECONDS)
            
            logger.info(f"Loaded settings: max_positions={self.max_open_positions}, alert_age={self.alert_max_age_seconds}, validation={self.validation_rules}")
            
        except Exception as e:
            logger.error(f"Error loading settings from settings.json: {e}")
            # Default values
            self.validation_rules = {
                'check_same_day_trades': True,
                'check_open_position_limit': True,
                'check_existing_position': True,
                'check_alert_timestamp': True,
                'check_dividend_date': True
            }
            self.max_open_positions = MAX_OPEN_POSITIONS
            self.alert_max_age_seconds = ALERT_MAX_AGE_SECONDS
    
    def process_alert(self, alert_message, timestamp=None):
        """
        Process an alert from TradingView
        
        Args:
            alert_message (str): The alert message
            timestamp (float, optional): Timestamp of the alert. Defaults to current time.
            
        Returns:
            dict: Result of the trade execution
        """
        if timestamp is None:
            timestamp = time.time()
        
        alert_time = datetime.fromtimestamp(timestamp)
        now = datetime.now()
        
        # Validate alert age if required
        if self.validation_rules['check_alert_timestamp']:
            if (now - alert_time).total_seconds() > self.alert_max_age_seconds:
                logger.warning(f"Alert is too old: {alert_message}")
                return {"status": "error", "message": "Alert is too old"}
        
        # Parse the alert message
        parse_result = self.trade_calculator.parse_alert_message(alert_message)
        if not parse_result:
            return {"status": "error", "message": "Failed to parse alert message"}
        
        ticker, direction, opening_price, atr_values = parse_result
        
        # Validate the trade
        validation_error = self._validate_trade(ticker)
        if validation_error:
            return validation_error
            
        # Get EPIC code for the ticker from CSV
        epic = self.get_epic(ticker)
        if not epic:
            return {"status": "error", "message": f"No IG EPIC code found for {ticker} in CSV"}
        
        # Get current IG price for normalization
        market_details = self.ig_client._get_market_details(epic)
        if not market_details:
            return {"status": "error", "message": f"Failed to get market details for {ticker}"}
        
        # IG tarafından sağlanan güncel fiyat bilgilerini al
        current_price = market_details.get('current_price', 0)
        bid_price = market_details.get('bid', 0)
        offer_price = market_details.get('offer', 0)
        
        if not current_price:
            return {"status": "error", "message": f"Failed to get current price for {ticker}"}
        
        # Fiyat bilgilerini detaylı şekilde logla
        logger.info(f"Processing alert for {ticker}: TV Price={opening_price}, IG Price={current_price}")
        logger.info(f"IG Bid/Offer: Bid={bid_price}, Offer={offer_price}")
        
        # JSON formatında fiyat bilgilerini logla (hata ayıklama için)
        ig_prices_json = {
            "prices": {
                "bid": bid_price,
                "current_price": current_price,
                "offer": offer_price
            },
            "tv_price": opening_price,
            "ticker": ticker,
            "epic": epic
        }
        logger.info(f"IG prices JSON format: {json.dumps(ig_prices_json)}")
        
        # Calculate trade parameters with price normalization
        trade_params = self.trade_calculator.calculate_trade_parameters(
            ticker, direction, opening_price, atr_values, ig_price=current_price
        )
        
        if not trade_params:
            return {"status": "error", "message": f"Failed to calculate trade parameters for {ticker}"}
        
        # Log the IG price information
        trade_params['ig_prices'] = {
            'bid': bid_price,
            'offer': offer_price,
            'current_price': current_price
        }
        
        # Execute the trade
        result = self._execute_trade(ticker, trade_params)
        
        # Record the trade if successful
        if result.get('status') == 'success':
            self.today_trades[ticker] = {
                'time': datetime.now(),
                'direction': trade_params['direction']
            }
            
        return result
    
    def _validate_trade(self, ticker):
        """
        Validate if a trade should be executed
        
        Args:
            ticker (str): The ticker symbol
            
        Returns:
            dict: Validation error or None if validation passed
        """
        # Check if we have the ticker data
        if self.ticker_data.empty:
            return {"status": "error", "message": "Ticker data not loaded"}
        
        # Check if the ticker exists in our data
        ticker_row = self.ticker_data[self.ticker_data['Symbol'] == ticker]
        if ticker_row.empty:
            return {"status": "error", "message": f"Ticker {ticker} not found in configuration"}
        
        # Get EPIC code for the ticker from CSV
        epic = self.get_epic(ticker)
        if not epic:
            return {"status": "error", "message": f"No IG EPIC code found for {ticker} in CSV"}
        
        # Check if position already exists for this ticker (if enabled)
        if self.validation_rules['check_existing_position']:
            positions = self.get_all_positions()
            for position in positions.get('positions', []):
                if position.get('epic') == epic:
                    return {"status": "error", "message": f"Position already exists for {ticker}"}
        
        # Check for same-day trades (if enabled)
        if self.validation_rules['check_same_day_trades']:
            if ticker in self.today_trades:
                trade_time = self.today_trades[ticker]['time']
                return {"status": "error", "message": f"Already traded {ticker} today at {trade_time.strftime('%H:%M:%S')}"}
        
        # Check maximum open positions (if enabled)
        if self.validation_rules['check_open_position_limit']:
            positions = self.get_all_positions()
            if len(positions.get('positions', [])) >= self.max_open_positions:
                return {"status": "error", "message": f"Maximum open positions limit ({self.max_open_positions}) reached"}
        
        # Check for dividend date (if enabled)
        if self.validation_rules['check_dividend_date']:
            if is_dividend_date(ticker, self.ticker_data):
                dividend_date = ticker_row['Next dividend date'].values[0]
                return {"status": "error", "message": f"Today is a dividend date for {ticker} ({dividend_date})"}
        
        return None
    
    def get_epic(self, symbol):
        """
        Get the EPIC code for a symbol from CSV data only
        
        Args:
            symbol (str): The ticker symbol
            
        Returns:
            str: The EPIC code or None if not found
        """
        # Try to get from CSV
        ticker_row = self.ticker_data[self.ticker_data['Symbol'] == symbol]
        if not ticker_row.empty and ticker_row['IG EPIC'].values[0] != '?':
            epic = ticker_row['IG EPIC'].values[0]
            logger.info(f"Using EPIC {epic} for {symbol} from CSV")
            return epic
        
        logger.error(f"No EPIC found in CSV for {symbol}")
        return None
    
    def _execute_trade(self, ticker, trade_params):
        """
        Execute a trade with the given parameters
        
        Args:
            ticker (str): The ticker symbol
            trade_params (dict): The trade parameters
            
        Returns:
            dict: Result of the trade execution
        """
        # Get the IG EPIC code for the ticker
        epic = self.get_epic(ticker)
        if not epic:
            return {"status": "error", "message": f"No IG EPIC code found for {ticker}"}
        
        try:
            # Her zaman LIMIT emirleri kullanacağız - 7/24 çalışması için
            logger.info(f"LIMIT emri oluşturuluyor: {ticker} için {trade_params['direction']}")
            
            # IG platformundan piyasa detaylarını al
            market_details = self.ig_client._get_market_details(epic)
            if not market_details:
                logger.error(f"Market details alınamadı: {ticker}")
                return {"status": "error", "message": f"Failed to get market details for {ticker}"}
                
            # IG'den gelen fiyat bilgilerini al
            current_price = market_details.get('current_price', 0)
            market_status = market_details.get('market_status', 'CLOSED')
            bid_price = market_details.get('bid', 0)
            offer_price = market_details.get('offer', 0)
            
            # API'den alınan minimum stop distance değeri
            min_stop_distance = market_details.get('min_stop_distance', 0)
            if min_stop_distance == 0:
                # Varsayılan değer: fiyatın %1'i
                min_stop_distance = current_price * 0.01
                logger.warning(f"Min stop distance bilgisi alınamadı, varsayılan olarak fiyatın %1'i kullanılıyor: {min_stop_distance}")
            else:
                logger.info(f"Market min stop distance: {min_stop_distance}")
            
            # TradingView'den gelen orijinal fiyat ve hesaplanan fiyat seviyesi
            original_price = trade_params['original_price']
            price_level = trade_params['price_level']
            
            # IG fiyatı ve TV fiyatı formatı arasında fark varsa ölçeklendirme faktörünü hesapla
            ig_format_multiplier = 1.0
            
            if current_price > 0 and price_level > 0:
                # Ondalık basamak farkını bul - önemli bir format farkı varsa bu sayıları ölçeklendirmemiz gerekiyor
                ig_digits = len(str(int(current_price)))
                tv_digits = len(str(int(price_level)))
                digit_diff = ig_digits - tv_digits
                
                if abs(digit_diff) >= 2:
                    # Format farkı var - ölçeklendirme faktörünü belirle
                    ig_format_multiplier = 10 ** digit_diff
                    logger.info(f"IG Format multiplier: {ig_format_multiplier} (based on IG:{ig_digits} - TV:{tv_digits} = {digit_diff} digits)")
                else:
                    logger.info(f"No significant format difference detected between IG price ({current_price}) and TV price level ({price_level})")
            
            # ADIM 2: Giriş fiyatını IG formatına dönüştür
            ig_formatted_level = price_level * ig_format_multiplier
            limit_level = round(ig_formatted_level, 4)
            logger.info(f"IG formatted level: {ig_formatted_level} (TV price {price_level} * {ig_format_multiplier})")
            
            # ADIM 3: Stop loss ve limit mesafelerini hesapla
            # Öncelikle trade_calculator'dan gelen orijinal hesaplamaları alalım
            original_stop_distance = trade_params['stop_distance']
            original_limit_distance = trade_params['limit_distance']
            
            # Log orijinal değerleri
            logger.info(f"Original calculator values - Stop: {original_stop_distance}, Limit: {original_limit_distance}")
            
            # ÖNEMLİ - YÜKSEK FİYATLI HİSSELER İÇİN IG API'YE GÖNDERME FORMATI
            # Her şeyin aynı ölçekte olduğundan emin olalım
            # Yüksek fiyatlar için IG'nin API'sinde format farkı var, bu farkı düzeltiyoruz
            
            # Önce format düzeltmesi uyguluyoruz
            if current_price >= 100 and limit_level >= 100:
                # Yüksek fiyatlı hisse - stop/limit değerlerini normalize et
                final_stop_distance = original_stop_distance  # Zaten doğru formatta
                final_limit_distance = original_limit_distance  # Zaten doğru formatta
                
                # Mesafe değerlerinin fiyat ile uyumlu olduğundan emin ol
                price_ratio = current_price / limit_level
                if abs(price_ratio - 1.0) > 0.1:  # Fiyat oranı %10'dan fazla farklıysa
                    logger.warning(f"Price ratio {price_ratio} indicates format mismatch, adjusting distances")
                    final_stop_distance = original_stop_distance * price_ratio
                    final_limit_distance = original_limit_distance * price_ratio
                
                logger.info(f"High price stock - using direct distance values: Stop={final_stop_distance}, Limit={final_limit_distance}")
            else:
                # Normal fiyat aralığı - ölçeklendirme gerekiyorsa uygula
                if ig_format_multiplier != 1.0:
                    final_stop_distance = original_stop_distance * ig_format_multiplier
                    final_limit_distance = original_limit_distance * ig_format_multiplier
                    logger.info(f"Scaled distances - Stop: {final_stop_distance}, Limit: {final_limit_distance}")
                else:
                    final_stop_distance = original_stop_distance
                    final_limit_distance = original_limit_distance
                    logger.info(f"No scaling needed for distances, using original values")
            
            # Minimum mesafeyi kontrol et - IG API'nin kabul edeceği minimum mesafe
            min_distance = max(min_stop_distance, current_price * 0.001)  # Fiyatın en az %0.1'i veya API min değeri
            
            # Mesafelerin çok küçük olmamasını sağla - sadece gerçekten çok küçükse minimum değeri kullan
            if final_stop_distance < min_distance:
                logger.warning(f"Stop distance ({final_stop_distance}) too small. Using: {min_distance}")
                final_stop_distance = min_distance
                
            if final_limit_distance < min_distance:
                logger.warning(f"Limit distance ({final_limit_distance}) too small. Using: {min_distance}")
                final_limit_distance = min_distance
                                
            # BUY/SELL işlemlerinde beklenen seviyeleri hesapla
            # Her iki işlem için de API'ye MESAFE değerlerini (pozitif) gönder, API kendisi seviyeleri hesaplar
            if trade_params['direction'] == 'BUY':
                # Alış (BUY) işleminde stop aşağıda, limit yukarıda olur
                expected_stop_level = limit_level - final_stop_distance
                expected_limit_level = limit_level + final_limit_distance
            else:
                # Satış (SELL) işleminde stop yukarıda, limit aşağıda olur
                expected_stop_level = limit_level + final_stop_distance
                expected_limit_level = limit_level - final_limit_distance
                
            logger.info(f"Beklenen seviyeler: Stop={expected_stop_level}, Limit={expected_limit_level}")
            logger.info(f"Hesaplanan mesafeler: Stop={final_stop_distance} (original: {original_stop_distance}), Limit={final_limit_distance} (original: {original_limit_distance})")
            
            # IG API her zaman pozitif mesafe değeri bekler
            # Değerler pozitif olmalı, yönlendirmeyi API kendisi yapar
            final_stop_distance = abs(final_stop_distance)
            final_limit_distance = abs(final_limit_distance)
            
            # Format sorununu çözmek için son bir kontrol
            # eğer limitDistance ya da stopDistance çok büyükse bunları düzelt
            if final_stop_distance > 1000:
                logger.warning(f"Stop distance {final_stop_distance} is too large, reducing by factor of 100")
                final_stop_distance = final_stop_distance / 100
            
            if final_limit_distance > 1000:
                logger.warning(f"Limit distance {final_limit_distance} is too large, reducing by factor of 100")
                final_limit_distance = final_limit_distance / 100
            
            # ADIM 5: Tüm bilgileri logla
            price_info = {
                "original_price": original_price,
                "calculated_price_level": price_level,
                "ig_format_multiplier": ig_format_multiplier,
                "ig_formatted_level": ig_formatted_level,
                "final_limit_level": limit_level,
                "ig_current_price": current_price,
                "ig_bid_price": bid_price,
                "ig_offer_price": offer_price,
                "original_stop_distance": original_stop_distance,
                "original_limit_distance": original_limit_distance,
                "calculated_stop_distance": final_stop_distance,
                "calculated_limit_distance": final_limit_distance,
                "min_stop_distance": min_stop_distance,
                "stop_level": expected_stop_level,
                "limit_level": expected_limit_level
            }
            
            logger.info(f"Fiyat dönüştürme bilgileri: {json.dumps(price_info)}")
            
            logger.info(f"İşlem detayları:")
            logger.info(f"Piyasa durumu: {market_status}, IG Fiyatı: {current_price}")
            logger.info(f"TradingView fiyatı: {original_price}, Hesaplanan Fiyat Seviyesi: {price_level}")
            logger.info(f"IG Formatında Limit Seviyesi: {limit_level}")
            logger.info(f"Yön: {trade_params['direction']}, Boyut: {trade_params['position_size']}")
            logger.info(f"Stop Distance: {final_stop_distance}")
            logger.info(f"Limit Distance: {final_limit_distance}")
            
            # ADIM 6: Pozisyon oluştur
            # IG API mesafeleri (distance) kullanıyor seviyeler (level) değil
            
            # *** SON KONTROL ***
            # Değerlerin makul aralıklarda olduğundan emin olalım
            position_size = trade_params['position_size']
            
            # Örneğin Serco için işlem boyutu doğrulaması:
            # entry_price = 176.851, position_size = 56.5
            # 176.851 * 56.5 = 9992 GBP (yaklaşık 10000 GBP'lik pozisyon)
            # Bu durumda işlem boyutu doğru ve ayarlanmamalı
            trade_value_gbp = limit_level * position_size
            logger.info(f"Trade value check: {limit_level} * {position_size} = £{trade_value_gbp:.2f}")
            
            # İşlem değeri makul sınırlar içinde olmalı (genelde 5000-15000 GBP arası)
            MAX_EXPECTED_TRADE_VALUE = 15000  # £15,000 maksimum
            
            # Yüksek fiyatlı hisse kontrolü
            if limit_level > 100 and trade_value_gbp > MAX_EXPECTED_TRADE_VALUE:
                # Bu bir yüksek fiyatlı hisse ve pozisyon değeri çok büyük
                # Pozisyon boyutunu düşür
                adjusted_size = round(MAX_EXPECTED_TRADE_VALUE / limit_level, 1)
                logger.warning(f"Position value {trade_value_gbp} is too large. Adjusting size from {position_size} to {adjusted_size}")
                position_size = adjusted_size
            
            # Mesafelerin doğru ölçekte olduğunu kontrol et
            # Eğer limit fiyatının %10'undan büyükse, muhtemelen ölçekleme sorunu var
            max_reasonable_distance = limit_level * 0.1  # Fiyatın %10'u
            
            if final_stop_distance > max_reasonable_distance:
                logger.warning(f"Stop distance {final_stop_distance} is suspiciously large (>{max_reasonable_distance}). Adjusting.")
                final_stop_distance = round(final_stop_distance / 100, 1)
                
            if final_limit_distance > max_reasonable_distance:
                logger.warning(f"Limit distance {final_limit_distance} is suspiciously large (>{max_reasonable_distance}). Adjusting.")
                final_limit_distance = round(final_limit_distance / 100, 1)
            
            # IG API için değerleri formatla
            # IG API fazla ondalık basamak kabul etmiyor - size, stop_distance ve limit_distance değerlerini yuvarlayalım
            position_size = round(position_size, 1)  # Sadece 1 ondalık basamak
            final_stop_distance = round(final_stop_distance, 1)  # Sadece 1 ondalık basamak
            final_limit_distance = round(final_limit_distance, 1)  # Sadece 1 ondalık basamak
            
            # Son durumu logla
            logger.info(f"FINAL VALUES - Size: {position_size}, Stop: {final_stop_distance}, Limit: {final_limit_distance}")
            
            # API çağrısını yap
            result = self.ig_client.create_position(
                epic=epic,
                direction=trade_params['direction'],
                size=position_size,
                limit_level=limit_level,  # Giriş fiyatı
                limit_distance=final_limit_distance,  # Take profit mesafesi
                stop_distance=final_stop_distance,  # Stop loss mesafesi
                use_limit_order=True
            )
            
            # API yanıtını detaylı şekilde logla
            logger.info(f"IG API yanıtı: {json.dumps(result)}")
            
            if result.get('status') == 'success':
                # İşlem başarılı - günlük işlem takibine ekle
                self.today_trades[ticker] = {
                    "time": datetime.now(),
                    "params": trade_params,
                    "epic": epic,
                    "deal_reference": result.get('deal_reference')
                }
                
                # Başarılı sonucu döndür
                return {
                    "status": "success",
                    "message": f"LIMIT order created for {ticker}",
                    "deal_reference": result.get('deal_reference'),
                    "epic": epic,
                    "direction": trade_params['direction'],
                    "entry_price": limit_level,
                    "original_price": original_price,
                    "current_ig_price": current_price,
                    "size": position_size,
                    "stop_distance": final_stop_distance,
                    "limit_distance": final_limit_distance,
                    "order_type": "LIMIT"
                }
            else:
                # Hata detaylarını zenginleştir
                error_code = result.get('error_code', 'UNKNOWN')
                error_reason = result.get('reason', 'Unknown error')
                
                # Bazı yaygın hata kodları için daha anlaşılır mesajlar ekle
                error_details = ""
                if "ATTACHED_ORDER_LEVEL_ERROR" in error_reason:
                    error_details = "ATTACHED_ORDER_LEVEL_ERROR: Stop veya limit seviyeleri uygun değil. Değerler çok yakın olabilir."
                elif "INSTRUMENT_NOT_TRADEABLE" in error_reason:
                    error_details = "INSTRUMENT_NOT_TRADEABLE: Enstrüman şu anda işleme kapalı veya ticaret dışı olabilir."
                elif "MARKET_CLOSED" in error_reason:
                    error_details = "MARKET_CLOSED: Piyasa kapalı durumda."
                elif "INSUFFICIENT_FUNDS" in error_reason:
                    error_details = "INSUFFICIENT_FUNDS: Hesapta yeterli bakiye yok."
                elif "POSITION_ALREADY_EXISTS_IN_OPPOSITE_DIRECTION" in error_reason:
                    error_details = "Karşıt yönde bir pozisyon zaten mevcut."
                
                return {
                    "status": "error",
                    "message": f"Failed to create order: {error_reason}",
                    "error_code": error_code,
                    "error_details": error_details,
                    "ticker": ticker,
                    "epic": epic,
                    "direction": trade_params['direction'],
                    "entry_price": limit_level,
                    "original_price": original_price,
                    "current_ig_price": current_price
                }
            
        except Exception as e:
            logger.error(f"Error executing trade: {e}")
            return {"status": "error", "message": f"Error executing trade: {str(e)}", "ticker": ticker}
    
    def check_position_status(self, deal_reference=None, ticker=None):
        """
        Check the status of a position by deal reference or ticker
        
        Args:
            deal_reference (str, optional): The deal reference returned by create_position
            ticker (str, optional): The ticker symbol for the position
            
        Returns:
            dict: Position status details or error message
        """
        if not deal_reference and not ticker:
            return {"status": "error", "message": "Must provide either deal_reference or ticker"}
        
        # If ticker is provided but no deal reference, try to find the deal reference from today's trades
        if ticker and not deal_reference:
            if ticker in self.today_trades:
                deal_reference = self.today_trades[ticker].get('deal_reference')
                if not deal_reference:
                    return {"status": "error", "message": f"No deal reference found for ticker {ticker}"}
            else:
                return {"status": "error", "message": f"No trade found today for ticker {ticker}"}
        
        # Check the status using the IG API
        status = self.ig_client.check_deal_status(deal_reference)
        
        if status is None:
            return {"status": "error", "message": f"Failed to retrieve status for deal reference {deal_reference}"}
        
        if status.get('status') == 'NOT_FOUND':
            return {"status": "error", "message": f"No position found with deal reference {deal_reference}"}
        
        return {
            "status": "success",
            "position_status": status.get('status'),
            "deal_id": status.get('dealId'),
            "deal_reference": deal_reference,
            "direction": status.get('direction'),
            "profit": status.get('profit'),
            "details": status
        }
    
    def get_all_positions(self):
        """
        Get all open positions
        
        Returns:
            dict: All open positions or error message
        """
        positions = self.ig_client.get_open_positions()
        
        if positions is None:
            return {"status": "error", "message": "Failed to get open positions from IG Markets"}
        
        # Format the positions in a more readable way
        formatted_positions = []
        for position in positions:
            market = position.get('market', {})
            pos = position.get('position', {})
            
            formatted_positions.append({
                "epic": market.get('epic'),
                "instrument_name": market.get('instrumentName'),
                "deal_id": pos.get('dealId'),
                "direction": pos.get('direction'),
                "size": pos.get('size'),
                "open_level": pos.get('level'),
                "profit": position.get('market', {}).get('profit', {}).get('value'),
                "created_date": pos.get('createdDate')
            })
        
        return {
            "status": "success",
            "position_count": len(formatted_positions),
            "positions": formatted_positions
        }
    
    def get_transaction_history(self, days=7, max_results=50):
        """
        Get transaction history for the past X days
        
        Args:
            days (int): Number of days to look back
            max_results (int): Maximum number of transactions to return
            
        Returns:
            dict: Transaction history or error message
        """
        # Calculate date range
        to_date = datetime.now()
        from_date = to_date - timedelta(days=days)
        
        # Format dates for API
        from_date_str = from_date.strftime("%Y-%m-%d")
        to_date_str = to_date.strftime("%Y-%m-%d")
        
        # Get transaction history from IG
        transactions = self.ig_client.get_transaction_history(
            from_date=from_date_str,
            to_date=to_date_str,
            max_results=max_results
        )
        
        if transactions is None:
            return {"status": "error", "message": "Failed to get transaction history from IG Markets"}
        
        # Format the transactions
        formatted_transactions = []
        for transaction in transactions:
            formatted_transactions.append({
                "date": transaction.get('dateUtc'),
                "transaction_type": transaction.get('transactionType'),
                "instrument_name": transaction.get('instrumentName'),
                "epic": transaction.get('epic'),
                "reference": transaction.get('reference'),
                "opening_level": transaction.get('openLevel'),
                "closing_level": transaction.get('closeLevel'),
                "profit": transaction.get('profitAndLoss'),
                "currency": transaction.get('currency'),
                "size": transaction.get('size'),
                "direction": transaction.get('direction')
            })
        
        return {
            "status": "success",
            "transaction_count": len(formatted_transactions),
            "transactions": formatted_transactions
        }
    
    def get_activity_history(self, days=7, max_results=50):
        """
        Get activity history for the past X days
        
        Args:
            days (int): Number of days to look back
            max_results (int): Maximum number of activities to return
            
        Returns:
            dict: Activity history or error message
        """
        # Calculate date range
        to_date = datetime.now()
        from_date = to_date - timedelta(days=days)
        
        # Format dates for API
        from_date_str = from_date.strftime("%Y-%m-%d")
        to_date_str = to_date.strftime("%Y-%m-%d")
        
        # Get activity history from IG
        activities = self.ig_client.get_activity_history(
            from_date=from_date_str,
            to_date=to_date_str,
            max_results=max_results
        )
        
        if activities is None:
            return {"status": "error", "message": "Failed to get activity history from IG Markets"}
        
        # Format the activities
        formatted_activities = []
        for activity in activities:
            formatted_activities.append({
                "date": activity.get('date'),
                "activity_type": activity.get('type'),
                "status": activity.get('status'),
                "description": activity.get('description'),
                "deal_id": activity.get('details', {}).get('dealId'),
                "deal_reference": activity.get('details', {}).get('dealReference'),
                "epic": activity.get('details', {}).get('epic'),
                "market_name": activity.get('details', {}).get('marketName'),
                "size": activity.get('details', {}).get('size'),
                "direction": activity.get('details', {}).get('direction'),
                "level": activity.get('details', {}).get('level'),
                "stop_level": activity.get('details', {}).get('stopLevel'),
                "limit_level": activity.get('details', {}).get('limitLevel')
            })
        
        return {
            "status": "success",
            "activity_count": len(formatted_activities),
            "activities": formatted_activities
        }
    
    def get_all_history(self, days=7, max_results=50):
        """
        Get comprehensive trading history including transactions, activities and positions
        
        Args:
            days (int): Number of days to look back
            max_results (int): Maximum number of records to return per type
            
        Returns:
            dict: Comprehensive trading history
        """
        try:
            # Log the start of the function
            logger.info(f"Getting comprehensive history for the past {days} days, max {max_results} results per type")
            
            # Get positions with detailed error handling
            try:
                logger.info("Getting open positions...")
                positions = self.get_all_positions()
                logger.info(f"Positions retrieved: {positions is not None}")
                if positions is None:
                    positions = {"status": "error", "positions": [], "position_count": 0}
            except Exception as e:
                logger.error(f"Error getting positions: {e}")
                positions = {"status": "error", "positions": [], "position_count": 0}
            
            # Get transactions with detailed error handling
            try:
                logger.info("Getting transaction history...")
                transactions = self.get_transaction_history(days, max_results)
                logger.info(f"Transactions retrieved: {transactions is not None}")
                if transactions is None:
                    transactions = {"status": "error", "transactions": [], "transaction_count": 0}
            except Exception as e:
                logger.error(f"Error getting transactions: {e}")
                transactions = {"status": "error", "transactions": [], "transaction_count": 0}
            
            # Get activities with detailed error handling
            try:
                logger.info("Getting activity history...")
                activities = self.get_activity_history(days, max_results)
                logger.info(f"Activities retrieved: {activities is not None}")
                if activities is None:
                    activities = {"status": "error", "activities": [], "activity_count": 0}
            except Exception as e:
                logger.error(f"Error getting activities: {e}")
                activities = {"status": "error", "activities": [], "activity_count": 0}
            
            # Ensure we have valid data structures
            pos_status = positions.get("status") if isinstance(positions, dict) else "error"
            tx_status = transactions.get("status") if isinstance(transactions, dict) else "error"
            act_status = activities.get("status") if isinstance(activities, dict) else "error"
            
            # Get data safely with fallbacks
            pos_list = positions.get("positions", []) if isinstance(positions, dict) else []
            pos_count = positions.get("position_count", 0) if isinstance(positions, dict) else 0
            tx_list = transactions.get("transactions", []) if isinstance(transactions, dict) else []
            tx_count = transactions.get("transaction_count", 0) if isinstance(transactions, dict) else 0
            act_list = activities.get("activities", []) if isinstance(activities, dict) else []
            act_count = activities.get("activity_count", 0) if isinstance(activities, dict) else 0
            
            # Combine into a comprehensive response
            result = {
                "status": "success" if (pos_status == "success" or tx_status == "success" or act_status == "success") else "error",
                "open_positions": pos_list,
                "position_count": pos_count,
                "transactions": tx_list,
                "transaction_count": tx_count,
                "activities": act_list,
                "activity_count": act_count,
                "days_history": days
            }
            
            logger.info(f"Comprehensive history retrieved successfully: positions={pos_count}, transactions={tx_count}, activities={act_count}")
            return result
            
        except Exception as e:
            logger.error(f"Error in get_all_history: {e}", exc_info=True)
            return {
                "status": "error",
                "message": f"Failed to get history data: {str(e)}",
                "open_positions": [],
                "position_count": 0,
                "transactions": [],
                "transaction_count": 0,
                "activities": [],
                "activity_count": 0,
                "days_history": days
            }
    
    def reset_daily_trades(self):
        """Reset the daily trades tracking at the start of a new day"""
        self.today_trades = {}
    
    def create_working_order(self, trade_params):
        """
        Creates a working order (limit order) for a specified instrument at a target price level
        
        Args:
            trade_params (dict): Dictionary containing trade parameters including:
                - epic (str): The IG epic code
                - direction (str): 'BUY' or 'SELL'
                - size (float): Position size
                - order_level (float): The target price level for the order
                - limit_distance (float, optional): Take profit distance in points
                - stop_distance (float, optional): Stop loss distance in points
                - guaranteed_stop (bool, optional): Whether to use a guaranteed stop
        
        Returns:
            dict: The result of the order including status and deal reference
        """
        required_params = ['epic', 'direction', 'size', 'order_level']
        for param in required_params:
            if param not in trade_params:
                logger.error(f"Missing required parameter: {param}")
                return {"status": "error", "reason": f"Missing required parameter: {param}"}
        
        # Extract parameters with defaults
        epic = trade_params['epic']
        direction = trade_params['direction']
        size = float(trade_params['size'])
        order_level = float(trade_params['order_level'])
        limit_distance = float(trade_params.get('limit_distance', 0))
        stop_distance = float(trade_params.get('stop_distance', 0))
        guaranteed_stop = trade_params.get('guaranteed_stop', False)
        
        logger.info(f"Creating working order: {direction} {epic} at level {order_level}")
        
        # Call the IG API to create a working order
        result = self.ig_client.create_working_order(
            epic=epic, 
            direction=direction,
            size=size,
            order_level=order_level,
            limit_distance=limit_distance,
            stop_distance=stop_distance,
            guaranteed_stop=guaranteed_stop
        )
        
        # API yanıtını detaylı loglayalım
        logger.info(f"Working order API yanıtı: {json.dumps(result)}")
        
        # API yanıtında deal bilgileri var mı kontrol edelim
        deal_reference = result.get('deal_reference')
        deal_id = result.get('deal_id')
        deal_status = result.get('deal_status')
        
        # Log the result
        if result.get("status") == "success":
            if deal_reference:
                logger.info(f"Working order created successfully. Deal reference: {deal_reference}")
            else:
                logger.warning("Working order created but no deal reference returned")
                
            # Trade günlüğüne eklemeyi deneyebiliriz, ancak önce trade_logger'ın var olup olmadığını kontrol edelim
            if hasattr(self, 'trade_logger'):
                # Save the trade details to CSV
                trade_details = {
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "type": "WORKING_ORDER",
                    "epic": epic,
                    "direction": direction,
                    "size": size,
                    "order_level": order_level,
                    "limit_distance": limit_distance,
                    "stop_distance": stop_distance,
                    "deal_reference": deal_reference or '',
                    "deal_id": deal_id or ''
                }
                self.trade_logger.log_trade(trade_details)
        else:
            error_reason = result.get('reason', 'Unknown error')
            logger.error(f"Failed to create working order: {error_reason}")
        
        # Eğer bir Epic veya sembol adı varsa bunu da yanıta ekleyelim
        if 'epic' in trade_params:
            result['epic'] = trade_params['epic']
        
        # Order parametrelerini de yanıta ekleyelim
        result['direction'] = direction
        result['size'] = size
        result['order_level'] = order_level
        result['limit_distance'] = limit_distance
        result['stop_distance'] = stop_distance
        
        return result 