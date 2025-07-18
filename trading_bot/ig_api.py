"""
IG Markets API integration for the Trading Bot
"""
import logging
import requests
import json
from datetime import datetime, timedelta
from trading_bot.config import IG_USERNAME, IG_PASSWORD, IG_API_KEY, IG_ACCOUNT_TYPE, TICKER_DATA_FILE
import os
import pandas as pd

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
        self.default_order_type = 'LIMIT'  # Default order type
    
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
        
        # IG API pageSize için 100'den büyük değerleri kabul etmiyor
        if max_results > 100:
            max_results = 100
            logger.info(f"Limiting pageSize to maximum allowed value: 100")
            
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
            'pageSize': str(max_results)
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
        
        # IG API pageSize için 100'den büyük değerleri kabul etmiyor
        if max_results > 100:
            max_results = 100
            logger.info(f"Limiting pageSize to maximum allowed value: 100")
        
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
            'pageSize': str(max_results),
            'detailed': 'true'
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
    
    def create_position(self, epic, direction, size, price=None, stop=None, limit=None, use_limit_order=None, expiry=None):
        """
        Create a new position
        
        Args:
            epic (str): The EPIC code for the instrument
            direction (str): 'BUY' or 'SELL'
            size (float): Position size in GBP
            price (float, optional): Entry price for limit orders
            stop (float, optional): Stop loss price
            limit (float, optional): Take profit price
            use_limit_order (bool, optional): Whether to use limit order. If None, uses default_order_type
            expiry (str, optional): Position expiry, default is "DFB" (Daily Funded Bet)
            
        Returns:
            dict: Response from IG API
        """
        if not self._ensure_session():
            logger.error("Failed to create position - no valid session")
            return {"status": "error", "reason": "No valid session"}
            
        # Determine order type
        if use_limit_order is None:
            use_limit_order = (self.default_order_type == 'LIMIT')
            
        # Set default expiry if not provided
        if expiry is None:
            expiry = "DFB"  # Daily Funded Bet - default for stocks
            
        # Prepare the position data
        position_data = {
            "epic": epic,
            "direction": direction,
            "size": str(size),
            "orderType": "LIMIT" if use_limit_order else "MARKET",
            "guaranteedStop": False,
            "forceOpen": True,
            "expiry": expiry,
            "currencyCode": "GBP"  # Para birimi kodu - her zaman GBP kullanıyoruz
        }
        
        # Add price for limit orders
        if use_limit_order and price:
            position_data["level"] = str(price)
            
        # Add stop loss if provided
        if stop:
            position_data["stopLevel"] = str(stop)
            position_data["stopDistance"] = None
            
        # Add take profit if provided
        if limit:
            position_data["profitLevel"] = str(limit)
            position_data["profitDistance"] = None
        
        # Make the API request
        response = self.session.post(
            f"{self.BASE_URL}/positions/otc",
            headers=self.headers,
            json=position_data
        )
        
        if response.status_code != 200:
            logger.error(f"Failed to create position: {response.text}")
            return {"status": "error", "reason": f"API Error: {response.status_code}", "details": response.text}
            
        result = response.json()
        deal_reference = result.get('dealReference', '')
        logger.info(f"Position created successfully. Deal reference: {deal_reference}")
        
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
            "message": "Position created, no confirmation details available"
        }
    
    def _get_market_details(self, epic):
        """
        Get details for a specific market
        
        Args:
            epic (str): The instrument's EPIC code
            
        Returns:
            dict: Dictionary containing market details or None if failed
        """
        if not self._ensure_session():
            return None
            
        url = f"{self.BASE_URL}/markets/{epic}"
        
        # Version başlığını ayarla
        headers = self.headers.copy()
        headers['Version'] = '3'
        
        try:
            response = self.session.get(url, headers=headers)
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    
                    # Extract relevant details
                    snapshot = data.get('snapshot', {})
                    dealing_rules = data.get('dealingRules', {})
                
                    # Get bid/offer prices
                    bid = snapshot.get('bid')
                    offer = snapshot.get('offer')
                
                    # Calculate the current price as the midpoint
                    if bid is not None and offer is not None:
                        current_price = (bid + offer) / 2
                    else:
                        current_price = None
                        
                    # Get market status
                    market_status = snapshot.get('marketStatus', 'CLOSED')
                    
                    # Debugger
                    logger.info(f"Market details for {epic}:")
                    logger.info(f"Bid: {bid}, Offer: {offer}, Calculated Current Price: {current_price}")
                    logger.info(f"Market Status: {market_status}")
                    
                    # Return the market details
                    return {
                        'current_price': current_price,
                        'bid': bid,
                        'offer': offer,
                        'market_status': market_status,
                        'min_deal_size': dealing_rules.get('minDealSize', {}).get('value', 0.1),
                        'min_stop_distance': dealing_rules.get('minNormalStopOrLimitDistance', {}).get('value', 0),
                        'min_limit_distance': dealing_rules.get('minControlledRiskStopDistance', {}).get('value', 0)
                    }
                except Exception as e:
                    logger.error(f"Error parsing market details for {epic}: {e}")
                    return None
            else:
                self._log_error_response(response, f"Failed to get market details for {epic}")
                return None
                
        except Exception as e:
            logger.error(f"Exception while getting market details for {epic}: {e}")
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
        
        # IG API her zaman pozitif mesafe değerleri bekler
        stop_distance = abs(float(stop_distance)) if stop_distance else 0
        limit_distance = abs(float(limit_distance)) if limit_distance else 0
        
        logger.info(f"Using positive distances: Stop={stop_distance}, Limit={limit_distance}")
        
        # Expiry değeri için varsayılan "DFB" (Daily Funded Bet) kullanılır
        # DFB genellikle hisse senetleri için kullanılır ve açık kalabilir
        if not expiry:
            expiry = "DFB"
        
        payload = {
            "epic": epic,
            "expiry": expiry,
            "direction": direction,
            "size": f"{round(float(size), 2):.2f}",
            "orderType": "MARKET",
            "timeInForce": "FILL_OR_KILL",
            "guaranteedStop": False,
            "forceOpen": True,
            "currencyCode": "GBP"
        }
        
        # Only add stop/limit if they're non-zero
        if stop_distance > 0:
            payload["stopDistance"] = f"{round(stop_distance, 2):.2f}"
            
        if limit_distance > 0:
            payload["limitDistance"] = f"{round(limit_distance, 2):.2f}"
        
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
        Get the EPIC code for a given symbol. First checks CSV file, then falls back to API search.
        
        Args:
            symbol (str): The ticker symbol (e.g., ASX_DLY:IAG)
            
        Returns:
            str: EPIC code or None if not found
        """
        if not symbol:
            logger.error("Symbol cannot be empty")
            return None

        # First try to get EPIC from CSV file
        try:
            if os.path.exists(TICKER_DATA_FILE):
                df = pd.read_csv(TICKER_DATA_FILE)
                if 'Symbol' in df.columns and 'IG EPIC' in df.columns:
                    # Find the row with matching symbol
                    row = df[df['Symbol'] == symbol]
                    if not row.empty:
                        epic = row.iloc[0]['IG EPIC']
                        # Check if EPIC is valid (not '?' or NaN)
                        if pd.notna(epic) and epic != '?':
                            logger.info(f"Found EPIC in CSV file: {epic} for {symbol}")
                            return str(epic)
                        else:
                            logger.info(f"Found symbol in CSV but EPIC is not set: {symbol}")
                    else:
                        logger.info(f"Symbol not found in CSV: {symbol}")
        except Exception as e:
            logger.error(f"Error reading CSV file: {e}")

        # If we get here, we need to search via API
        logger.info(f"Falling back to API search for symbol: {symbol}")

        # Exchange ve ticker'ı ayır
        parts = symbol.split(':')
        if len(parts) != 2:
            logger.error(f"Invalid symbol format: {symbol}. Expected format: EXCHANGE:TICKER")
            return None
        
        exchange, ticker = parts
        
        # Exchange prefix mapping - IG'nin kullandığı prefix'ler
        exchange_prefixes = {
            'ASX_DLY': ['AU.D.', 'IX.D.AU'],  # Avustralya
            'LSE_DLY': ['IX.D.LS', 'UK.D.'],  # Londra
            'BATS': ['CS.D.', 'US.D.'],       # BATS US
            'TSX_DLY': ['CA.D.'],             # Toronto
            'HKEX_DLY': ['HK.D.'],            # Hong Kong
            'TSE_DLY': ['IX.D.JP', 'JP.D.'],  # Tokyo
            'XETR_DLY': ['IX.D.DAX', 'DE.D.'] # Deutsche Börse
        }
        
        # Get the expected prefixes for this exchange
        expected_prefixes = exchange_prefixes.get(exchange, [])
        if not expected_prefixes:
            logger.error(f"Unsupported exchange: {exchange}")
            return None
        
        # Search for the market
        markets = self.search_market(ticker)
        if not markets:
            logger.error(f"No markets found for {ticker}")
            return None
        
        # Log all found markets for debugging
        logger.info(f"Found {len(markets)} markets for {symbol}:")
        for market in markets:
            logger.info(f"EPIC: {market.get('epic')}, Name: {market.get('instrumentName')}, Type: {market.get('instrumentType')}")
        
        # First try: Look for exact match with exchange prefix and DAILY.IP
        for prefix in expected_prefixes:
            for market in markets:
                epic = market.get('epic', '')
                if isinstance(epic, str) and epic.startswith(prefix) and epic.endswith('.DAILY.IP'):
                    logger.info(f"Found exact match EPIC: {epic} (prefix: {prefix})")
                    return epic
        
        # Second try: Look for any match with exchange prefix
        for prefix in expected_prefixes:
            for market in markets:
                epic = market.get('epic', '')
                if isinstance(epic, str) and epic.startswith(prefix):
                    logger.info(f"Found exchange match EPIC: {epic} (prefix: {prefix})")
                    return epic
        
        # Third try: Look for any DAILY.IP market that contains the ticker
        for market in markets:
            epic = market.get('epic', '')
            if isinstance(epic, str) and epic.endswith('.DAILY.IP') and ticker.upper() in epic.upper():
                logger.warning(f"Using partial match EPIC: {epic} - may not be correct exchange")
                return epic
        
        # If nothing found, return None
        logger.error(f"No suitable EPIC found for {symbol}")
        return None
    
    def _ensure_session(self):
        """Ensure the session is active, login if needed"""
        if not (self.cst and self.security_token):
            return self.login()
        return True
    
    def is_connected(self):
        """
        Check if the client is connected to the IG API
        
        Returns:
            bool: True if connected, False otherwise
        """
        if not (self.cst and self.security_token):
            # No session tokens, try logging in
            return self.login()
            
        try:
            # Make a simple request to verify the session is still valid
            url = f"{self.BASE_URL}/accounts"
            headers = self.headers.copy()
            headers['Version'] = '1'
            
            response = self.session.get(url, headers=headers)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Error checking connection: {e}")
            return False
    
    def create_working_order(self, epic, direction, size, level, stop=None, limit=None, use_limit_order=None):
        """
        Create a working order
        
        Args:
            epic (str): The EPIC code for the instrument
            direction (str): 'BUY' or 'SELL'
            size (float): Position size in GBP
            level (float): Entry price level
            stop (float, optional): Stop loss price
            limit (float, optional): Take profit price
            use_limit_order (bool, optional): Whether to use limit order. If None, uses default_order_type
            
        Returns:
            dict: Response from IG API
        """
        if not self._ensure_session():
            logger.error("Failed to create working order - no valid session")
            return {"status": "error", "reason": "No valid session"}
            
        # Determine order type
        if use_limit_order is None:
            use_limit_order = (self.default_order_type == 'LIMIT')
            
        # Prepare the working order data
        order_data = {
            "epic": epic,
            "direction": direction,
            "size": str(size),
            "type": "LIMIT", # Working order type
            "level": str(level),
            "timeInForce": "GOOD_TILL_CANCELLED",
            "guaranteedStop": False,
            "forceOpen": True,
            "currencyCode": "GBP",
            "expiry": "DFB"  # Daily Funded Bet - required for working orders
        }
        
        # Add stop loss if provided
        if stop:
            order_data["stopLevel"] = str(stop)
            
        # Add take profit if provided
        if limit:
            order_data["limitLevel"] = str(limit)
        
        # Log the request data
        logger.info(f"Creating working order with data: {json.dumps(order_data)}")
        
        # Make the API request
        response = self.session.post(
            f"{self.BASE_URL}/workingorders/otc",
            headers=self.headers,
            json=order_data
        )
        
        # Log the full response
        logger.info(f"Working order response status: {response.status_code}")
        logger.info(f"Working order response body: {response.text}")
        
        if response.status_code != 200:
            logger.error(f"Failed to create working order: {response.text}")
            return {"status": "error", "reason": f"API Error: {response.status_code}", "details": response.text}
            
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
    
    def set_default_order_type(self, order_type):
        """Set the default order type (LIMIT or MARKET)"""
        if order_type not in ['LIMIT', 'MARKET']:
            raise ValueError("Order type must be either 'LIMIT' or 'MARKET'")
        self.default_order_type = order_type
    
    def get_working_orders(self):
        """Get all working orders"""
        if not self._ensure_session():
            return None
        
        url = f"{self.BASE_URL}/workingorders"
        headers = self.headers.copy()
        headers['Version'] = '2'
        
        try:
            logger.info(f"Getting working orders from {url}")
            
            response = self.session.get(url, headers=headers)
            
            if response.status_code == 200:
                result = response.json()
                raw_orders = result.get('workingOrders', [])
                logger.info(f"Successfully retrieved {len(raw_orders)} working orders")
                
                # Format working orders with additional details
                orders = []
                for order in raw_orders:
                    working_order_data = order.get('workingOrderData', {})
                    market_data = order.get('marketData', {})
                    
                    # Extract stop and limit levels
                    stop_level = working_order_data.get('stopLevel')
                    if stop_level is None:
                        stop_level = working_order_data.get('stopDistance')
                    
                    limit_level = working_order_data.get('limitLevel')
                    if limit_level is None:
                        limit_level = working_order_data.get('limitDistance')
                    
                    orders.append({
                        "dealId": working_order_data.get('dealId'),
                        "epic": market_data.get('epic'),
                        "direction": working_order_data.get('direction'),
                        "size": working_order_data.get('size'),
                        "level": working_order_data.get('level'),
                        "stopLevel": stop_level,
                        "limitLevel": limit_level,
                        "orderType": working_order_data.get('type'),
                        "createdDate": working_order_data.get('createdDateUTC')
                    })
                
                return orders
            else:
                error_msg = ""
                try:
                    error_msg = response.json().get('errorCode', '')
                except:
                    error_msg = response.text
                logger.error(f"Failed to get working orders: {response.status_code} - {error_msg}")
                return None
                
        except Exception as e:
            logger.error(f"Exception while getting working orders: {e}")
            return None
            
    def cancel_working_order(self, deal_id):
        """
        Cancel a working order by deal ID
        
        Args:
            deal_id (str): The deal ID of the working order to cancel
            
        Returns:
            dict: Response from the API or None if failed
        """
        if not self._ensure_session():
            return None
        
        url = f"{self.BASE_URL}/workingorders/otc/{deal_id}"
        headers = self.headers.copy()
        headers['Version'] = '2'  # Use version 2 for deleting working orders
        headers['_method'] = 'DELETE'  # Required for DELETE operations
        
        try:
            logger.info(f"Cancelling working order with deal ID: {deal_id}")
            
            # DELETE request to cancel the working order
            response = self.session.delete(url, headers=headers)
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"Successfully cancelled working order: {deal_id}")
                return result
            else:
                error_msg = ""
                try:
                    error_msg = response.json().get('errorCode', '')
                except:
                    error_msg = response.text
                logger.error(f"Failed to cancel working order: {response.status_code} - {error_msg}")
                return None
                
        except Exception as e:
            logger.error(f"Exception while cancelling working order: {e}")
            return None 