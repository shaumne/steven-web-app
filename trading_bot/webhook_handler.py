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
    
    def __init__(self, ig_api, settings_manager):
        """Initialize the webhook handler"""
        self.ig_api = ig_api
        self.settings_manager = settings_manager
        self.trade_manager = TradeManager()
        self.last_reset_day = datetime.now().day
    
    def update_settings(self, settings=None):
        """
        Update settings in the trade manager
        
        Args:
            settings (dict): New settings to apply
        """
        logger.info("Updating settings in webhook handler")
        # Reload settings in trade manager
        self.trade_manager.load_settings()
    
    def process_webhook(self, data):
        """
        Process incoming webhook data from TradingView
        
        Args:
            data (dict): Webhook data containing trade information
            
        Returns:
            dict: Response with status and details
        """
        try:
            # Extract required fields
            symbol = data.get('symbol')
            direction = data.get('direction')
            price = data.get('price')
            stop = data.get('stop')
            limit = data.get('limit')
            size = data.get('size')
            message = data.get('message', '')
            
            # Validate required fields
            if not all([symbol, direction]):
                return {
                    'status': 'error',
                    'message': 'Missing required fields: symbol and direction are required'
                }
                
            # Get trading settings
            settings = self.settings_manager.get_settings()
            trading_settings = settings.get('trading', {})
            
            # Get default order type from settings
            default_order_type = trading_settings.get('default_order_type', 'LIMIT')
            
            # Convert symbol to EPIC
            epic = self._convert_symbol_to_epic(symbol)
            if not epic:
                return {
                    'status': 'error',
                    'message': f'Invalid symbol: {symbol}'
                }
                
            # Validate direction
            if direction not in ['BUY', 'SELL']:
                return {
                    'status': 'error',
                    'message': f'Invalid direction: {direction}. Must be BUY or SELL'
                }
                
            # Get position size
            if not size:
                size = self._get_position_size(epic)
                
            # Create position
            result = self.ig_api.create_position(
                epic=epic,
                direction=direction,
                size=size,
                price=price,
                stop=stop,
                limit=limit,
                use_limit_order=(default_order_type == 'LIMIT')
            )
            
            # Log the result
            self.logger.info(f"Webhook processed: {message}")
            self.logger.info(f"Position result: {result}")
            
            return {
                'status': 'success',
                'message': 'Webhook processed successfully',
                'details': result
            }
            
        except Exception as e:
            self.logger.error(f"Error processing webhook: {str(e)}")
            return {
                'status': 'error',
                'message': f'Error processing webhook: {str(e)}'
            }
            
    def _convert_symbol_to_epic(self, symbol):
        """
        Convert TradingView symbol to IG EPIC
        
        Args:
            symbol (str): TradingView symbol (e.g. 'MARKET:SYMBOL')
            
        Returns:
            str: IG EPIC code or None if not found
        """
        try:
            # Remove 'MARKET:' prefix if present
            if ':' in symbol:
                symbol = symbol.split(':')[1]
                
            # Get ticker data
            ticker_data = self.settings_manager.get_ticker_data()
            
            # Find matching EPIC
            match = ticker_data[ticker_data['Symbol'] == symbol]
            if not match.empty:
                return match.iloc[0]['IG EPIC']
                
            return None
            
        except Exception as e:
            self.logger.error(f"Error converting symbol to EPIC: {str(e)}")
            return None
            
    def _get_position_size(self, epic):
        """
        Get default position size for an instrument
        
        Args:
            epic (str): IG EPIC code
            
        Returns:
            float: Position size in GBP
        """
        try:
            # Get ticker data
            ticker_data = self.settings_manager.get_ticker_data()
            
            # Find matching instrument
            match = ticker_data[ticker_data['IG EPIC'] == epic]
            if not match.empty:
                return float(match.iloc[0]['Postion Size Max GBP'])
                
            # Default size if not found
            return 100.0
            
        except Exception as e:
            self.logger.error(f"Error getting position size: {str(e)}")
            return 100.0
    
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