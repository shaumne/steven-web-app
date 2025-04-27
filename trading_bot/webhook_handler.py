"""
Webhook handler for processing incoming alerts from TradingView
"""
import logging
import json
import time
from datetime import datetime
from trading_bot.trade_manager import TradeManager

logger = logging.getLogger(__name__)

class WebhookHandler:
    """
    Handler for incoming webhook requests from TradingView
    """
    
    def __init__(self):
        """Initialize the webhook handler"""
        self.trade_manager = TradeManager()
        self.last_reset_day = datetime.now().day
    
    def process_webhook(self, request_data):
        """
        Process a webhook request
        
        Args:
            request_data (dict): The request data from the webhook
            
        Returns:
            dict: Result of processing the webhook
        """
        # Check if we need to reset daily trades
        self._check_reset_daily_trades()
        
        try:
            # Extract the alert message from the request data
            force_test_mode = False
            
            if isinstance(request_data, dict):
                # If it's already a dictionary (e.g., from a JSON request)
                alert_message = request_data.get('message')
                timestamp = request_data.get('timestamp', time.time())
                # Sadece açıkça test_mode=True gönderilmişse test modunda çalıştır
                force_test_mode = request_data.get('test_mode', False)
            elif isinstance(request_data, str):
                # If it's a string, assume it's the alert message
                alert_message = request_data.strip()
                timestamp = time.time()
            else:
                logger.error(f"Invalid request data format: {type(request_data)}")
                return {"status": "error", "message": "Invalid request data format"}
            
            if not alert_message:
                logger.error("No alert message found in request data")
                return {"status": "error", "message": "No alert message found in request data"}
            
            # Log the incoming alert
            logger.info(f"Received alert: {alert_message}")
            
            # Process the alert with the trade manager
            # Varsayılan olarak her zaman gerçek işlem yap
            # Ancak 'test_mode' parametresi açıkça True olarak gönderilmişse test yap
            if force_test_mode:
                logger.info("TEST MODE: Processing alert but no real trade will be executed")
                result = self._test_process_alert(alert_message, timestamp)
            else:
                # Normal işlem yap - gerçek pozisyon aç
                logger.info("LIVE MODE: Processing alert for real trade execution")
                result = self.trade_manager.process_alert(alert_message, timestamp)
            
            # Log the result
            if result.get('status') == 'success':
                logger.info(f"Successfully processed alert: {result}")
            else:
                logger.warning(f"Failed to process alert: {result}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error processing webhook: {e}")
            return {"status": "error", "message": f"Error processing webhook: {str(e)}"}
    
    def _test_process_alert(self, alert_message, timestamp):
        """
        Process an alert in test mode (no real trade execution)
        
        Args:
            alert_message (str): The alert message
            timestamp (float): Timestamp of the alert
            
        Returns:
            dict: Simulated processing result
        """
        # Parse the alert message
        parse_result = self.trade_manager.trade_calculator.parse_alert_message(alert_message)
        if not parse_result:
            return {"status": "error", "message": "Failed to parse alert message"}
        
        ticker, direction, opening_price, atr_values = parse_result
        
        # Try to get the EPIC code (main purpose of this test)
        epic = self.trade_manager.get_epic(ticker)
        
        # Calculate trade parameters
        trade_params = self.trade_manager.trade_calculator.calculate_trade_parameters(
            ticker, direction, opening_price, atr_values
        )
        
        if not trade_params:
            return {"status": "error", "message": f"Failed to calculate trade parameters for {ticker}"}
        
        # Return test result
        return {
            "status": "success",
            "message": f"TEST MODE: Processed alert for {ticker}",
            "ticker": ticker,
            "direction": direction,
            "epic": epic,
            "trade_params": trade_params,
            "test_mode": True
        }
    
    def _check_reset_daily_trades(self):
        """Check if we need to reset daily trades tracking"""
        today = datetime.now().day
        if today != self.last_reset_day:
            logger.info("Resetting daily trades tracking")
            self.trade_manager.reset_daily_trades()
            self.last_reset_day = today 

    def process_alert(self, data):
        """
        Process the alert data from TradingView
        """
        try:
            logger.info(f"Processing webhook data: {data}")

            # Extract the essential parameters
            required_fields = ['epic', 'direction', 'size']
            for field in required_fields:
                if field not in data:
                    logger.error(f"Missing required field: {field}")
                    return {"status": "error", "reason": f"Missing required field: {field}"}

            # Check if this is a market order or a working order
            if 'order_level' in data:
                # This is a working order
                return self._process_working_order(data)
            else:
                # This is a market order
                return self._process_market_order(data)

        except Exception as e:
            logger.error(f"Error processing webhook data: {str(e)}")
            return {"status": "error", "reason": str(e)}

    def _process_market_order(self, data):
        """
        Process a market order
        """
        # Extract trade parameters
        trade_params = {
            'epic': data['epic'],
            'direction': data['direction'],
            'size': float(data['size']),
            'limit_distance': float(data.get('limit_distance', 0)),
            'stop_distance': float(data.get('stop_distance', 0)),
            'guaranteed_stop': data.get('guaranteed_stop', 'false').lower() == 'true'
        }

        # Execute the trade
        logger.info(f"Executing trade with parameters: {trade_params}")
        result = self.trade_manager.place_trade(trade_params)
        return result

    def _process_working_order(self, data):
        """
        Process a working order (limit order)
        """
        # Extract trade parameters
        trade_params = {
            'epic': data['epic'],
            'direction': data['direction'],
            'size': float(data['size']),
            'order_level': float(data['order_level']),
            'limit_distance': float(data.get('limit_distance', 0)),
            'stop_distance': float(data.get('stop_distance', 0)),
            'guaranteed_stop': data.get('guaranteed_stop', 'false').lower() == 'true'
        }

        # Create the working order
        logger.info(f"Creating working order with parameters: {trade_params}")
        result = self.trade_manager.create_working_order(trade_params)
        return result 