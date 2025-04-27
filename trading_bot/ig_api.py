"""
IG Markets API integration for the Trading Bot
"""
import logging
import requests
import json
from datetime import datetime, timedelta
from trading_bot.config import IG_USERNAME, IG_PASSWORD, IG_API_KEY, IG_ACCOUNT_TYPE

logger = logging.getLogger(__name__)

class IGClient:
    """Client for interacting with the IG Markets API"""
    
    def __init__(self):
        # Demo veya live API URL'sini ayarla
        if IG_ACCOUNT_TYPE and IG_ACCOUNT_TYPE.upper() == 'DEMO':
            self.BASE_URL = "https://demo-api.ig.com/gateway/deal"
            logger.info(f"Using DEMO API endpoint: {self.BASE_URL}")
        else:
            self.BASE_URL = "https://api.ig.com/gateway/deal"
            logger.info(f"Using LIVE API endpoint: {self.BASE_URL}")
            
        self.session = requests.Session()
        self.session_token = None
        self.cst = None
        self.security_token = None
        self.headers = {
            'Content-Type': 'application/json; charset=utf-8',
            'Accept': 'application/json; charset=UTF-8',
            'X-IG-API-KEY': IG_API_KEY,
            'Version': '2'  # Default API version
        }
        self.account_type = IG_ACCOUNT_TYPE
        self.trade_history = {}  # İşlem geçmişini depolamak için sözlük
    
    def login(self):
        """Login to IG Markets API"""
        url = f"{self.BASE_URL}/session"
        payload = {
            "identifier": IG_USERNAME,
            "password": IG_PASSWORD,
            "encryptedPassword": False
        }
        
        # Set specific version for login endpoint
        headers = self.headers.copy()
        headers['Version'] = '2'
        
        # Debug logs
        logger.info("=" * 50)
        logger.info("LOGIN ATTEMPT")
        logger.info(f"Account type: {self.account_type}")
        logger.info(f"Base URL: {self.BASE_URL}")
        logger.info(f"URL: {url}")
        logger.info(f"Username: {IG_USERNAME}")
        logger.info(f"API Key length: {len(IG_API_KEY)} chars")
        logger.info(f"Headers: {json.dumps({k: ('***' if k in ['X-IG-API-KEY', 'password'] else v) for k, v in headers.items()})}")
        
        try:
            # Make the login request
            response = self.session.post(
                url,
                data=json.dumps(payload),
                headers=headers
            )
            
            logger.info(f"Response status code: {response.status_code}")
            logger.info(f"Response headers: {dict(response.headers)}")
            
            # Log response text - mask sensitive data
            response_text = response.text
            if len(response_text) > 500:
                logger.info(f"Response content (truncated): {response_text[:500]}...")
            else:
                logger.info(f"Response content: {response_text}")
                
            logger.info("=" * 50)
            
            if response.status_code == 200:
                data = response.json()
                
                # Save session details
                self.session_token = data.get('clientSessionToken')
                self.cst = response.headers.get('CST')
                self.security_token = response.headers.get('X-SECURITY-TOKEN')
                
                if not self.cst or not self.security_token:
                    logger.error("Authentication tokens not found in response")
                    return False
                
                # Update headers for subsequent requests
                self.headers['CST'] = self.cst
                self.headers['X-SECURITY-TOKEN'] = self.security_token
                
                logger.info(f"Successfully logged in to IG Markets API. CST: {self.cst[:5]}..., X-SECURITY-TOKEN: {self.security_token[:5]}...")
                return True
            else:
                error_msg = ""
                try:
                    error_msg = response.json().get('errorCode', '')
                except:
                    error_msg = response.text
                    
                logger.error(f"Failed to log in to IG Markets API: {response.status_code} - {error_msg}")
                return False
                
        except Exception as e:
            logger.error(f"Exception during IG Markets API login: {e}")
            return False
    
    def get_account_info(self):
        """Get account information"""
        if not self._ensure_session():
            return None
        
        url = f"{self.BASE_URL}/accounts"
        headers = self.headers.copy()
        headers['Version'] = '1'
        
        try:
            response = self.session.get(url, headers=headers)
            
            if response.status_code == 200:
                return response.json()
            else:
                error_msg = ""
                try:
                    error_msg = response.json().get('errorCode', '')
                except:
                    error_msg = response.text
                logger.error(f"Failed to get account info: {response.status_code} - {error_msg}")
                return None
                
        except Exception as e:
            logger.error(f"Exception while getting account info: {e}")
            return None
    
    def get_open_positions(self):
        """Get all open positions"""
        if not self._ensure_session():
            return None
        
        url = f"{self.BASE_URL}/positions"
        headers = self.headers.copy()
        headers['Version'] = '2'
        
        try:
            logger.info(f"Getting open positions from {url}")
            logger.info(f"Headers: {json.dumps({k: ('***' if k in ['X-IG-API-KEY', 'CST', 'X-SECURITY-TOKEN'] else v) for k, v in headers.items()})}")
            
            response = self.session.get(url, headers=headers)
            
            logger.info(f"Response status code: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                positions = result.get('positions', [])
                logger.info(f"Successfully retrieved {len(positions)} open positions")
                return positions
            else:
                error_msg = ""
                try:
                    error_msg = response.json().get('errorCode', '')
                except:
                    error_msg = response.text
                logger.error(f"Failed to get open positions: {response.status_code} - {error_msg}")
                return None
                
        except Exception as e:
            logger.error(f"Exception while getting open positions: {e}")
            return None
    
    def get_position_by_deal_id(self, deal_id):
        """
        Get details of a specific position by deal ID
        
        Args:
            deal_id (str): The deal ID of the position
            
        Returns:
            dict: Position details or None if not found
        """
        if not self._ensure_session():
            return None
        
        # First, get all open positions
        positions = self.get_open_positions()
        
        if positions is None:
            return None
        
        # Find the position with the matching deal ID
        for position in positions:
            if position.get('position', {}).get('dealId') == deal_id:
                return position
        
        logger.warning(f"No position found with deal ID: {deal_id}")
        return None
    
    def get_transaction_history(self, from_date=None, to_date=None, max_results=20):
        """
        Get transaction history
        
        Args:
            from_date (str, optional): From date in format YYYY-MM-DD. Defaults to 7 days ago.
            to_date (str, optional): To date in format YYYY-MM-DD. Defaults to today.
            max_results (int, optional): Maximum number of results. Defaults to 20.
            
        Returns:
            list: Transaction history or None if failed
        """
        if not self._ensure_session():
            return None
        
        # Set default dates if not provided
        if from_date is None:
            from_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        if to_date is None:
            to_date = datetime.now().strftime("%Y-%m-%d")
        
        url = f"{self.BASE_URL}/history/transactions"
        headers = self.headers.copy()
        headers['Version'] = '2'
        
        params = {
            'type': 'ALL',
            'from': from_date,
            'to': to_date,
            'pageSize': max_results
        }
        
        try:
            response = self.session.get(url, params=params, headers=headers)
            
            if response.status_code == 200:
                return response.json().get('transactions', [])
            else:
                error_msg = ""
                try:
                    error_msg = response.json().get('errorCode', '')
                except:
                    error_msg = response.text
                logger.error(f"Failed to get transaction history: {response.status_code} - {error_msg}")
                return None
                
        except Exception as e:
            logger.error(f"Exception while getting transaction history: {e}")
            return None
    
    def get_activity_history(self, from_date=None, to_date=None, max_results=20):
        """
        Get activity history including deal status
        
        Args:
            from_date (str, optional): From date in format YYYY-MM-DD. Defaults to 7 days ago.
            to_date (str, optional): To date in format YYYY-MM-DD. Defaults to today.
            max_results (int, optional): Maximum number of results. Defaults to 20.
            
        Returns:
            list: Activity history or None if failed
        """
        if not self._ensure_session():
            return None
        
        # Set default dates if not provided
        if from_date is None:
            from_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        if to_date is None:
            to_date = datetime.now().strftime("%Y-%m-%d")
        
        url = f"{self.BASE_URL}/history/activity"
        headers = self.headers.copy()
        headers['Version'] = '3'
        
        params = {
            'from': from_date,
            'to': to_date,
            'pageSize': max_results
        }
        
        try:
            response = self.session.get(url, params=params, headers=headers)
            
            if response.status_code == 200:
                return response.json().get('activities', [])
            else:
                error_msg = ""
                try:
                    error_msg = response.json().get('errorCode', '')
                except:
                    error_msg = response.text
                logger.error(f"Failed to get activity history: {response.status_code} - {error_msg}")
                return None
                
        except Exception as e:
            logger.error(f"Exception while getting activity history: {e}")
            return None
    
    def check_deal_status(self, deal_reference):
        """
        Check the status of a deal by its reference
        
        Args:
            deal_reference (str): The deal reference returned by create_position
            
        Returns:
            dict: Deal status or None if failed
        """
        if not self._ensure_session():
            return None
        
        # First try to get the deal confirmation
        confirmation = self.get_deal_confirmation(deal_reference)
        
        if confirmation:
            # Get the deal ID from the confirmation
            deal_id = confirmation.get('dealId')
            if deal_id:
                # Check if this is an open position
                position = self.get_position_by_deal_id(deal_id)
                if position:
                    return {
                        'status': 'OPEN',
                        'dealReference': deal_reference,
                        'dealId': deal_id,
                        'direction': position.get('position', {}).get('direction'),
                        'size': position.get('position', {}).get('size'),
                        'profit': position.get('position', {}).get('profit', {}).get('value'),
                        'details': position
                    }
            
            # If we couldn't find an open position, check activity history
            activities = self.get_activity_history()
            if activities:
                for activity in activities:
                    if activity.get('details', {}).get('dealReference') == deal_reference:
                        return {
                            'status': activity.get('status'),
                            'dealReference': deal_reference,
                            'dealId': activity.get('details', {}).get('dealId'),
                            'activity_type': activity.get('type'),
                            'details': activity
                        }
            
            # If we have a confirmation but no position or activity, return what we know
            return {
                'status': 'CONFIRMED',
                'dealReference': deal_reference,
                'dealId': deal_id,
                'direction': confirmation.get('direction'),
                'details': confirmation
            }
        
        # If we couldn't find any information, return a not found status
        return {
            'status': 'NOT_FOUND',
            'dealReference': deal_reference
        }
    
    def create_position(self, epic, direction, size, limit_distance=0, stop_distance=0, use_limit_order=False, limit_level=None, expiry="DFB"):
        """
        Create a position (market order or limit order).
        
        Args:
            epic (str): The instrument's Epic code
            direction (str): BUY or SELL
            size (float): Trade size
            limit_distance (float, optional): Take profit distance in points
            stop_distance (float, optional): Stop loss distance in points
            use_limit_order (bool, optional): If True, creates a limit order instead of a market order
            limit_level (float, optional): Price level for limit orders (required if use_limit_order is True)
            expiry (str, optional): Position expiry (default: DFB - daily)
            
        Returns:
            dict: Position creation result with status and details
        """
        # Validate inputs for limit orders
        if use_limit_order and limit_level is None:
            error_msg = "limit_level must be provided for limit orders"
            logger.error(error_msg)
            return {"status": "error", "reason": error_msg}
            
        # Create either a market or limit position based on the use_limit_order flag
        if use_limit_order:
            logger.info(f"Creating LIMIT position for {epic}, direction: {direction}, size: {size}, limit_level: {limit_level}")
            result = self._create_limit_position(
                epic=epic,
                direction=direction,
                size=size,
                limit_level=limit_level,
                limit_distance=limit_distance,
                stop_distance=stop_distance,
                expiry=expiry
            )
        else:
            logger.info(f"Creating MARKET position for {epic}, direction: {direction}, size: {size}")
            result = self._create_market_position(
                epic=epic,
                direction=direction,
                size=size,
                limit_distance=limit_distance,
                stop_distance=stop_distance,
                expiry=expiry
            )
            
        # If trade was successful, store it in historical records
        if result["status"] == "success":
            deal_ref = result.get("deal_reference")
            if deal_ref:
                self.trade_history[deal_ref] = result
                
        return result
    
    def _get_market_details(self, epic):
        """
        Get market details including current price, market state, and minimum distances
        
        Args:
            epic (str): The IG epic code for the instrument
            
        Returns:
            dict: Market details or None if failed
        """
        if not self._ensure_session():
            return None
            
        market_url = f"{self.BASE_URL}/markets/{epic}"
        market_headers = self.headers.copy()
        market_headers['Version'] = '3'  # Version 3 provides more detailed market data
        
        try:
            market_response = self.session.get(market_url, headers=market_headers)
            if market_response.status_code == 200:
                market_data = market_response.json()
                
                # Extract data
                snapshot = market_data.get('snapshot', {})
                dealing_rules = market_data.get('dealingRules', {})
                instrument = market_data.get('instrument', {})
                
                # Get current bid/offer prices
                bid = snapshot.get('bid', 0)
                offer = snapshot.get('offer', 0)
                
                # Get market status
                market_status = snapshot.get('marketStatus', 'CLOSED')
                
                # Get minimum stop and limit distances
                min_normal_stop = dealing_rules.get('minNormalStopOrLimitDistance', {})
                min_stop_distance = 0
                min_limit_distance = 0
                
                if min_normal_stop:
                    min_distance_unit = min_normal_stop.get('unit', 'POINTS')
                    min_distance_value = float(min_normal_stop.get('value', 0))
                    
                    if min_distance_unit == 'PERCENTAGE':
                        # Convert percentage to points based on current price
                        mid_price = (bid + offer) / 2
                        min_stop_distance = (mid_price * min_distance_value) / 100
                        min_limit_distance = min_stop_distance
                    else:
                        min_stop_distance = min_distance_value
                        min_limit_distance = min_distance_value
                
                # Get point size/value
                lot_size = instrument.get('lotSize', 1)
                currency = instrument.get('currencies', [{}])[0].get('code', 'GBP')
                contract_size = instrument.get('contractSize', 1)
                
                logger.info(f"Market details for {epic} - Bid: {bid}, Offer: {offer}, Status: {market_status}")
                logger.info(f"Min stop distance: {min_stop_distance}, Min limit distance: {min_limit_distance}")
                
                return {
                    'bid': bid,
                    'offer': offer,
                    'current_price': (bid + offer) / 2,  # Mid price
                    'market_status': market_status,
                    'min_stop_distance': min_stop_distance,
                    'min_limit_distance': min_limit_distance,
                    'lot_size': lot_size,
                    'currency': currency,
                    'contract_size': contract_size
                }
            else:
                self._log_error_response(market_response, f"Failed to get market details for {epic}")
                return None
                
        except Exception as e:
            logger.error(f"Exception while getting market details: {e}")
            return None
    
    def _create_market_position(self, epic, direction, size, limit_distance, stop_distance, expiry):
        """
        Create a MARKET position for immediate execution
        
        Args:
            epic (str): The IG epic code for the instrument
            direction (str): 'BUY' or 'SELL'
            size (float): Position size
            limit_distance (float): Take profit distance in points
            stop_distance (float): Stop loss distance in points
            expiry (str): Position expiry
            
        Returns:
            dict: Response from the API with position details or error details
        """
        url = f"{self.BASE_URL}/positions/otc"
        headers = self.headers.copy()
        headers['Version'] = '2'
        
        # Ensure direction is uppercase
        direction = direction.upper()
        
        payload = {
            "epic": epic,
            "expiry": expiry,
            "direction": direction,
            "size": str(size),
            "orderType": "MARKET",
            "timeInForce": "FILL_OR_KILL",
            "guaranteedStop": False,
            "forceOpen": True,
            "currencyCode": "GBP"
        }
        
        # Only add stop/limit if they're non-zero
        if stop_distance > 0:
            payload["stopDistance"] = str(stop_distance)
        
        if limit_distance > 0:
            payload["limitDistance"] = str(limit_distance)
        
        logger.info(f"Creating MARKET {direction} position for {epic} with size {size}")
        logger.info(f"Stop distance: {stop_distance}, Limit distance: {limit_distance}")
        logger.info(f"Payload: {json.dumps({k: v for k, v in payload.items() if k not in ['epic']})}")
        
        try:
            response = self.session.post(
                url,
                data=json.dumps(payload),
                headers=headers
            )
            
            # Log the full response details
            logger.info(f"Market position response status: {response.status_code}")
            logger.info(f"Market position response body: {response.text}")
            
            if response.status_code == 200:
                data = response.json()
                deal_reference = data.get('dealReference')
                logger.info(f"Market position created successfully, deal reference: {deal_reference}")
                
                # Yanıtı başlat
                result = {
                    "status": "success",
                    "deal_reference": deal_reference,
                    "epic": epic,
                    "direction": direction,
                    "size": size,
                    "order_type": "LIMIT",
                    "limit_distance": limit_distance,
                    "stop_distance": stop_distance
                }
                
                # Get the deal confirmation for more details
                confirmation = self.get_deal_confirmation(deal_reference)
                if confirmation:
                    # Deal ID ve diğer detayları ekle
                    result["deal_id"] = confirmation.get('dealId')
                    result["deal_status"] = confirmation.get('status')
                    result["confirmation"] = confirmation
                
                return result
            else:
                error_response = {
                    "status": "error",
                    "epic": epic,
                    "direction": direction,
                    "size": size,
                    "order_type": "MARKET"
                }
                
                # Log and add error details
                self._log_error_response(response, "Failed to create market position")
                
                # Hata detaylarını yanıta ekle
                try:
                    error_data = response.json()
                    error_response["error_code"] = error_data.get('errorCode', '')
                    error_response["reason"] = error_data.get('reason', '')
                    error_response["error_details"] = error_data
                except:
                    error_response["error"] = response.text
                
                return error_response
                
        except Exception as e:
            logger.error(f"Exception while creating market position: {e}")
            return {
                "status": "error",
                "reason": f"Exception: {str(e)}",
                "epic": epic,
                "direction": direction,
                "size": size,
                "order_type": "MARKET"
            }
    
    def _log_error_response(self, response, message):
        """Helper method to log error responses from the API"""
        try:
            error_data = response.json()
            error_msg = error_data.get('errorCode', '')
            error_reason = error_data.get('reason', '')
            logger.error(f"{message}: {response.status_code} - {error_msg}")
            logger.error(f"Reason: {error_reason}")
            logger.error(f"Full error response: {json.dumps(error_data)}")
        except:
            logger.error(f"{message}: {response.status_code} - {response.text}")
    
    def get_deal_confirmation(self, deal_reference):
        """Get confirmation details for a deal"""
        if not self._ensure_session():
            return None
        
        url = f"{self.BASE_URL}/confirms/{deal_reference}"
        headers = self.headers.copy()
        headers['Version'] = '1'
        
        try:
            response = self.session.get(url, headers=headers)
            
            if response.status_code == 200:
                return response.json()
            else:
                error_msg = ""
                try:
                    error_msg = response.json().get('errorCode', '')
                except:
                    error_msg = response.text
                logger.error(f"Failed to get deal confirmation: {response.status_code} - {error_msg}")
                return None
                
        except Exception as e:
            logger.error(f"Exception while getting deal confirmation: {e}")
            return None
    
    def search_market(self, search_term):
        """
        Search for markets/instruments by a search term to get EPIC codes
        
        Args:
            search_term (str): Search term (usually the ticker symbol)
            
        Returns:
            list: List of matching markets or None if failed
        """
        if not self._ensure_session():
            return None
        
        url = f"{self.BASE_URL}/markets?searchTerm={search_term}"
        headers = self.headers.copy()
        headers['Version'] = '1'
        
        try:
            response = self.session.get(url, headers=headers)
            
            if response.status_code == 200:
                markets = response.json().get('markets', [])
                logger.info(f"Found {len(markets)} markets matching '{search_term}'")
                return markets
            else:
                error_msg = ""
                try:
                    error_msg = response.json().get('errorCode', '')
                except:
                    error_msg = response.text
                logger.error(f"Failed to search markets: {response.status_code} - {error_msg}")
                return None
                
        except Exception as e:
            logger.error(f"Exception while searching markets: {e}")
            return None
    
    def get_epic_from_symbol(self, symbol):
        """
        Get the EPIC code for a given symbol
        
        Args:
            symbol (str): The ticker symbol (e.g., BATS:PML)
            
        Returns:
            str: EPIC code or None if not found
        """
        # Extract exchange and ticker if in the format EXCHANGE:TICKER
        parts = symbol.split(':')
        search_term = parts[-1]  # Use the last part (the ticker)
        
        # Search for the market
        markets = self.search_market(search_term)
        
        if not markets:
            logger.error(f"No markets found for symbol: {symbol}")
            return None
        
        # Log found markets for debugging
        logger.info(f"Found {len(markets)} markets for {symbol}:")
        for i, market in enumerate(markets):
            epic = market.get('epic', '')
            instrument_name = market.get('instrumentName', '')
            market_id = market.get('marketId', '')
            expiry = market.get('expiry', '')
            instrument_type = market.get('instrumentType', '')
            
            logger.info(f"  {i+1}. EPIC: {epic}, Name: {instrument_name}, Market ID: {market_id}, Type: {instrument_type}, Expiry: {expiry}")
        
        # SPREADBET hesapları için uygun EPIC kodlarını bulma önceliği
        spreadbet_markets = []
        
        # Filter for potential spreadbet markets
        for market in markets:
            epic = market.get('epic', '')
            # Genellikle spreadbet epic kodları CS.D.* veya IX.D.* ile başlar
            # Ayrıca *DAILY.IP veya *CASH.IP ile biter
            if (epic.startswith(('CS.D.', 'IX.D.', 'KA.D.', 'UA.D.', 'UD.D.', 'UK.D.', 'UP.D.'))
                    or '.DAILY.IP' in epic 
                    or '.CASH.IP' in epic):
                spreadbet_markets.append(market)
        
        logger.info(f"Found {len(spreadbet_markets)} potential spreadbet markets for {symbol}")
        
        # Önce spreadbet marketlerde exchange eşleşmesi arama
        if len(parts) > 1 and spreadbet_markets:
            exchange = parts[0]
            
            # Try to find a spreadbet market with matching exchange
            for market in spreadbet_markets:
                market_name = market.get('instrumentName', '')
                market_exchange = market.get('marketId', '').split('.')[0]
                
                if (exchange.lower() in market_exchange.lower() or 
                    exchange.lower() in market_name.lower()):
                    epic = market.get('epic')
                    logger.info(f"Found spreadbet EPIC {epic} for {symbol} with exchange match")
                    return epic
        
        # If we found any spreadbet markets, return the first one
        if spreadbet_markets:
            epic = spreadbet_markets[0].get('epic')
            logger.info(f"Using spreadbet EPIC {epic} for {symbol} (first spreadbet match)")
            return epic
            
        # Eğer exchange belirtildiyse, tüm marketlerde eşleşme arama
        if len(parts) > 1:
            exchange = parts[0]
            
            # Try to find a market with matching exchange
            for market in markets:
                market_name = market.get('instrumentName', '')
                market_exchange = market.get('marketId', '').split('.')[0]
                
                if (exchange.lower() in market_exchange.lower() or 
                    exchange.lower() in market_name.lower()):
                    epic = market.get('epic')
                    logger.warning(f"Found EPIC {epic} for {symbol} with exchange match, but it may not be spreadbet compatible")
                    return epic
        
        # If we get here, just return the first result's EPIC with a warning
        if markets:
            epic = markets[0].get('epic')
            logger.warning(f"Using EPIC {epic} for {symbol} (first match), but it may not be spreadbet compatible")
            return epic
        
        return None
    
    def _ensure_session(self):
        """Ensure the session is active, login if needed"""
        if not (self.cst and self.security_token):
            return self.login()
        return True
    
    def create_working_order(self, epic, direction, size, order_level, limit_distance=0, stop_distance=0, guaranteed_stop=False, expiry=None):
        """
        Create a working order (limit order) at a specified price level
        
        Args:
            epic (str): The epic identifier for the instrument
            direction (str): The direction of the trade ('BUY' or 'SELL')
            size (float): The size of the trade
            order_level (float): The price level to execute the order at
            limit_distance (float, optional): The limit distance in points. Defaults to 0.
            stop_distance (float, optional): The stop distance in points. Defaults to 0.
            guaranteed_stop (bool, optional): Whether to use a guaranteed stop. Defaults to False.
            expiry (str, optional): The expiry time for the working order. Defaults to None (which results in 'DFB' for daily markets).
            
        Returns:
            dict: The response from the API containing deal reference if successful, or error details
        """
        if not self._ensure_session():
            logger.error("Failed to create working order - no valid session")
            return {"status": "error", "reason": "No valid session"}
        
        # Determine appropriate expiry
        if not expiry:
            # Set default expiry based on market type
            if 'DFB' in epic:
                expiry = 'DFB'  # Daily Funded Bet
            elif 'CFD' in epic:
                expiry = 'DFB'  # For CFDs, use daily by default
            else:
                expiry = 'GTC'  # Good Till Cancelled as fallback
        
        # Get market details to verify current price and minimum distances
        market_details = self._get_market_details(epic)
        if not market_details:
            return {"status": "error", "reason": "Failed to get market details"}
        
        current_price = market_details.get('current_price', 0)
        
        # Determine order type (LIMIT or STOP) based on direction and level
        order_type = "LIMIT"
        if direction == "BUY" and order_level > current_price:
            order_type = "STOP"
        elif direction == "SELL" and order_level < current_price:
            order_type = "STOP"
        
        logger.info(f"Creating {order_type} working order - Direction: {direction}, Price: {order_level}, Current price: {current_price}")
        
        # Build the payload
        payload = {
            "epic": epic,
            "expiry": expiry,
            "direction": direction,
            "size": str(size),
            "level": str(order_level),
            "type": order_type,
            "timeInForce": "GOOD_TILL_CANCELLED",
            "guaranteedStop": guaranteed_stop,
            "forceOpen": True,
            "currencyCode": "GBP"  # Varsayılan para birimi ekleniyor
        }
        
        # Add stop and limit if provided (and non-zero)
        if stop_distance and float(stop_distance) > 0:
            payload["stopDistance"] = str(stop_distance)
        
        if limit_distance and float(limit_distance) > 0:
            payload["limitDistance"] = str(limit_distance)
        
        # Create the working order
        working_order_url = f"{self.BASE_URL}/workingorders/otc"
        working_order_headers = self.headers.copy()
        working_order_headers['Version'] = '2'
        
        try:
            logger.info(f"Sending working order request: {json.dumps(payload, indent=2)}")
            response = self.session.post(working_order_url, headers=working_order_headers, data=json.dumps(payload))
            
            logger.info(f"Working order response status: {response.status_code}")
            logger.info(f"Working order response body: {response.text}")
            
            if response.status_code == 200:
                result = response.json()
                deal_reference = result.get('dealReference', '')
                logger.info(f"Working order created successfully. Deal reference: {deal_reference}")
                
                if deal_reference:
                    # Get the deal confirmation for more details
                    confirmation = self.get_deal_confirmation(deal_reference)
                    if confirmation:
                        deal_id = confirmation.get('dealId')
                        deal_status = confirmation.get('status')
                        return {
                            "status": "success", 
                            "deal_reference": deal_reference,
                            "deal_id": deal_id,
                            "deal_status": deal_status,
                            "confirmation": confirmation
                        }
                    
                # Even if we couldn't get confirmation, return success with the deal reference
                return {
                    "status": "success", 
                    "deal_reference": deal_reference,
                    "message": "Working order created, no confirmation details available"
                }
            else:
                self._log_error_response(response, "Failed to create working order")
                return {"status": "error", "reason": f"API Error: {response.status_code}", "details": response.text}
                
        except Exception as e:
            logger.error(f"Exception creating working order: {str(e)}")
            return {"status": "error", "reason": f"Exception: {str(e)}"}
    
    def _create_limit_position(self, epic, direction, size, limit_level, limit_distance=0, stop_distance=0, expiry="DFB"):
        """
        Create a LIMIT position (executes when market reaches the limit level).
        
        Args:
            epic (str): The instrument's Epic code
            direction (str): BUY or SELL
            size (float): Trade size
            limit_level (float): Price level for the limit order to trigger
            limit_distance (float, optional): Take profit distance in points
            stop_distance (float, optional): Stop loss distance in points
            expiry (str, optional): Position expiry (default: DFB - daily)
            
        Returns:
            dict: Limit order creation result with status and details
        """
        if not self._ensure_session():
            return {"status": "error", "reason": "No valid session"}
            
        # Önce market detaylarını alalım
        market_details = self._get_market_details(epic)
        if not market_details:
            return {"status": "error", "reason": "Failed to get market details"}
            
        market_status = market_details.get('market_status', 'CLOSED')
        current_price = market_details.get('current_price', 0)
        
        logger.info(f"Market status for {epic}: {market_status}, current price: {current_price}")
        
        # Piyasa açıksa positions/otc kullanabiliriz, kapalıysa workingorders/otc kullanmalıyız
        if market_status == 'TRADEABLE':
            # Piyasa açık - positions/otc endpoint'i ile limit emri oluştur
            logger.info(f"Market is OPEN - creating limit position with positions/otc endpoint")
            
            # Construct the payload for the API request
            payload = {
                "epic": epic,
                "expiry": expiry,
                "direction": direction,
                "size": str(size),
                "orderType": "LIMIT",
                "level": str(limit_level),
                "forceOpen": True,
                "guaranteedStop": False,
                "timeInForce": "EXECUTE_AND_ELIMINATE",
                "currencyCode": "GBP"
            }
            
            # Add stop and limit if provided
            if stop_distance > 0:
                payload["stopDistance"] = str(stop_distance)
                
            if limit_distance > 0:
                payload["limitDistance"] = str(limit_distance)
                
            # Define the API endpoint
            endpoint = f"{self.BASE_URL}/positions/otc"
            
        else:
            # Piyasa kapalı - workingorders/otc endpoint'i ile çalışan emir oluştur
            logger.info(f"Market is CLOSED - creating working order with workingorders/otc endpoint")
            
            # Determine order type (LIMIT/STOP)
            order_type = "LIMIT"
            
            # Construct the payload for the API request
            payload = {
                "epic": epic,
                "expiry": expiry,
                "direction": direction,
                "size": str(size),
                "level": str(limit_level),
                "type": order_type,
                "currencyCode": "GBP",
                "timeInForce": "GOOD_TILL_CANCELLED",
                "guaranteedStop": False,
                "forceOpen": True
            }
            
            # Add stop and limit if provided
            if stop_distance > 0:
                payload["stopDistance"] = str(stop_distance)
                
            if limit_distance > 0:
                payload["limitDistance"] = str(limit_distance)
                
            # Define the API endpoint
            endpoint = f"{self.BASE_URL}/workingorders/otc"
            
        # Version başlığını ayarla
        headers = self.headers.copy()
        headers['Version'] = '2'
        
        # Log request details (without the API key)
        safe_headers = dict(headers)
        if 'X-IG-API-KEY' in safe_headers:
            safe_headers['X-IG-API-KEY'] = '*****'
            
        logger.debug(f"Order request to {endpoint}")
        logger.debug(f"Headers: {safe_headers}")
        logger.debug(f"Payload: {payload}")
        
        try:
            # Make the API request
            response = self.session.post(
                endpoint,
                headers=headers,
                json=payload
            )
            
            logger.debug(f"API response status: {response.status_code}")
            logger.debug(f"API response body: {response.text}")
            
            # Check if the response is successful
            if response.status_code == 200:
                data = response.json()
                logger.info(f"Order created successfully: {data}")
                
                # Return the success response with order details
                return {
                    "status": "success",
                    "deal_id": data.get("dealId"),
                    "deal_reference": data.get("dealReference"),
                    "date": datetime.now().isoformat(),
                    "epic": epic,
                    "direction": direction,
                    "size": size,
                    "order_type": "LIMIT" if market_status == "TRADEABLE" else "WORKING_ORDER",
                    "limit_level": limit_level
                }
            else:
                # Try to extract error details from the response
                error_details = "Unknown error"
                try:
                    error_data = response.json()
                    error_details = error_data.get("errorCode", str(error_data))
                except Exception:
                    error_details = response.text
                
                logger.error(f"Failed to create order: {error_details}")
                return {
                    "status": "error",
                    "reason": f"API error ({response.status_code}): {error_details}",
                    "epic": epic,
                    "direction": direction,
                    "size": size,
                    "order_type": "LIMIT" if market_status == "TRADEABLE" else "WORKING_ORDER"
                }
                
        except Exception as e:
            logger.error(f"Exception in create order: {str(e)}")
            return {
                "status": "error",
                "reason": f"Exception: {str(e)}",
                "epic": epic,
                "direction": direction,
                "size": size,
                "order_type": "LIMIT" if market_status == "TRADEABLE" else "WORKING_ORDER"
            }
    
    def get_working_orders(self):
        """
        Get all working orders
        
        Returns:
            dict: API response with working orders
        """
        if not self._ensure_session():
            return {"workingOrders": []}
        
        url = f"{self.BASE_URL}/workingorders"
        headers = self.headers.copy()
        headers['Version'] = '2'
        
        try:
            response = self.session.get(url, headers=headers)
            if response.status_code == 200:
                return response.json()
            else:
                logging.error(f"Failed to get working orders: {response.status_code} - {response.text}")
                return {"workingOrders": []}
        except Exception as e:
            logging.error(f"Error getting working orders: {e}")
            return {"workingOrders": []} 