"""
Trade manager for handling trading operations
"""
import logging
import time
from datetime import datetime, timedelta
import pandas as pd
from trading_bot.ig_api import IGClient
from trading_bot.trade_calculator import TradeCalculator
from trading_bot.config import (
    MAX_OPEN_POSITIONS, ALERT_MAX_AGE_SECONDS, load_ticker_data, 
    is_dividend_date
)
import json

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
        self.max_open_positions = MAX_OPEN_POSITIONS
        self.epic_cache = {}  # Cache for EPIC codes to avoid repeated API calls
    
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
        
        # Validate alert age
        if (now - alert_time).total_seconds() > ALERT_MAX_AGE_SECONDS:
            logger.warning(f"Alert is too old: {alert_message}")
            return {"status": "error", "message": "Alert is too old"}
        
        # Parse the alert message
        parse_result = self.trade_calculator.parse_alert_message(alert_message)
        if not parse_result:
            return {"status": "error", "message": "Failed to parse alert message"}
        
        ticker, direction, opening_price, atr_values = parse_result
        
        # Perform pre-trade validations
        validation_result = self._validate_trade(ticker)
        if validation_result:
            return validation_result
        
        # Calculate trade parameters
        trade_params = self.trade_calculator.calculate_trade_parameters(
            ticker, direction, opening_price, atr_values
        )
        
        if not trade_params:
            return {"status": "error", "message": f"Failed to calculate trade parameters for {ticker}"}
        
        # Execute the trade
        return self._execute_trade(ticker, trade_params)
    
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
        
        # Check if we've already traded this ticker today
        if ticker in self.today_trades:
            return {"status": "error", "message": f"Already traded {ticker} today"}
        
        # Check if there's a dividend today
        if is_dividend_date(ticker, self.ticker_data):
            return {"status": "error", "message": f"Dividend date for {ticker} today, skipping trade"}
        
        # Check if we have too many open positions
        open_positions = self.ig_client.get_open_positions()
        if open_positions is None:
            return {"status": "error", "message": "Failed to get open positions from IG Markets"}
        
        if len(open_positions) >= self.max_open_positions:
            return {"status": "error", "message": f"Maximum open positions reached ({self.max_open_positions})"}
        
        # Get EPIC code for the ticker from API
        epic = self.get_epic(ticker)
        if not epic:
            return {"status": "error", "message": f"No IG EPIC code found for {ticker}"}
            
        # Check if we already have an open position for this ticker
        for position in open_positions:
            if position.get('market', {}).get('epic') == epic:
                return {"status": "error", "message": f"Already have an open position for {ticker}"}
        
        return None
    
    def get_epic(self, symbol):
        """
        Get the EPIC code for a symbol, using cache if available
        
        Args:
            symbol (str): The ticker symbol
            
        Returns:
            str: The EPIC code or None if not found
        """
        # Check if we have it in cache
        if symbol in self.epic_cache:
            return self.epic_cache[symbol]
        
        # Try to get from CSV first (for backward compatibility)
        ticker_row = self.ticker_data[self.ticker_data['Symbol'] == symbol]
        if not ticker_row.empty and ticker_row['IG EPIC'].values[0] != '?':
            epic = ticker_row['IG EPIC'].values[0]
            logger.info(f"Using EPIC {epic} for {symbol} from CSV")
            self.epic_cache[symbol] = epic
            return epic
        
        # Get from API if not available in CSV
        epic = self.ig_client.get_epic_from_symbol(symbol)
        
        # Cache the result if found
        if epic:
            self.epic_cache[symbol] = epic
            
        return epic
    
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
                logger.error(f"Market details alınamadı, limit emri için fiyat belirlenemedi: {ticker}")
                return {"status": "error", "message": f"Failed to get market details for {ticker}"}
                
            current_price = market_details.get('current_price', 0)
            market_status = market_details.get('market_status', 'CLOSED')
            
            logger.info(f"Piyasa durumu: {market_status}, Fiyat: {current_price} için {ticker}")
            
            # TradingView'dan gelen fiyat yerine GERÇEK piyasa fiyatına göre limit seviyesi ayarla
            limit_level = None
            
            # Yön ve piyasa durumuna göre uygun seviyeyi belirle
            if trade_params['direction'] == 'BUY':
                # Alış için, mevcut fiyattan birazcık aşağıda bir limit emri ver
                limit_level = current_price * 0.99  # %1 altında
                logger.info(f"BUY emri için limit seviyesi: {limit_level} (mevcut fiyat: {current_price})")
            else:  # SELL
                # Satış için, mevcut fiyattan birazcık yukarıda bir limit emri ver
                limit_level = current_price * 1.01  # %1 üstünde
                logger.info(f"SELL emri için limit seviyesi: {limit_level} (mevcut fiyat: {current_price})")
                
            # Limit fiyatını ondalık basamağı düzenle
            limit_level = round(limit_level, 2)  # 2 ondalık basamağa yuvarla
            logger.info(f"Ayarlanmış limit seviyesi: {limit_level} için {ticker}")
            
            # Orjinal trade parametrelerini sakla ancak entry_price bilgisini güncelle
            original_entry_price = trade_params.get('entry_price')
            logger.info(f"Orijinal TradingView fiyatı: {original_entry_price}, Gerçek piyasa fiyatı: {current_price}")
            
            # IG API'ye LIMIT emri gönder
            result = self.ig_client.create_position(
                epic=epic,
                direction=trade_params['direction'],
                size=trade_params['position_size'],
                limit_distance=trade_params['limit_distance'],
                stop_distance=trade_params['stop_distance'],
                use_limit_order=True,  # Her zaman LIMIT emri kullan
                limit_level=limit_level
            )
            
            if not result:
                logger.error(f"LIMIT emri oluşturulamadı: {ticker}")
                return {"status": "error", "message": f"Failed to create limit order for {ticker}"}
            
            # API yanıtını loglayalım daha detaylı
            logger.info(f"API yanıtı: {json.dumps(result)}")
            
            # API yanıtında deal_reference var mı kontrol edelim
            deal_reference = result.get('deal_reference')
            deal_id = result.get('deal_id')
            
            # Record the trade for today
            self.today_trades[ticker] = {
                "time": datetime.now(),
                "params": trade_params,
                "result": result,
                "epic": epic,  # Store the EPIC code for reference
                "deal_reference": deal_reference,
                "deal_id": deal_id,
                "original_entry_price": original_entry_price,
                "adjusted_limit_level": limit_level,
                "market_price": current_price
            }
            
            # Log success information
            if deal_reference:
                logger.info(f"LIMIT emri başarıyla oluşturuldu: {ticker}, Deal Reference: {deal_reference}")
            elif deal_id:
                logger.info(f"LIMIT emri başarıyla oluşturuldu: {ticker}, Deal ID: {deal_id}")
            else:
                logger.warning(f"LIMIT emri oluşturuldu ancak deal_reference veya deal_id alınamadı: {ticker}")
            
            response = {
                "status": "success",
                "message": f"LIMIT order created for {ticker}",
                "order_type": "LIMIT",
                "direction": trade_params['direction'],
                "size": trade_params['position_size'],
                "entry_price": trade_params['entry_price'],
                "stop_distance": trade_params['stop_distance'],
                "limit_distance": trade_params['limit_distance'],
                "epic": epic
            }
            
            # Eğer deal bilgisi gelirse ekleyelim
            if deal_reference:
                response["deal_reference"] = deal_reference
            if deal_id:
                response["deal_id"] = deal_id
                
            # API yanıtının konfirmasyon kısmı varsa ekleyelim
            if 'confirmation' in result:
                response['confirmation'] = result['confirmation']
                
            # Eğer deal_status bilgisi varsa ekleyelim
            if 'deal_status' in result:
                response['deal_status'] = result['deal_status']
                
            return response
            
        except Exception as e:
            logger.error(f"Error executing trade for {ticker}: {e}")
            return {"status": "error", "message": f"Error executing trade: {str(e)}"}
    
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