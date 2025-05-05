"""
Main application for the Trading Bot webhook server
"""
import os
import logging
import json
import time
import pandas as pd
import psutil
import datetime
from flask import Flask, request, jsonify, render_template, session, redirect, url_for, flash, send_file, abort
from werkzeug.security import check_password_hash
from flask_cors import CORS
from trading_bot.webhook_handler import WebhookHandler
from trading_bot.config import load_ticker_data
from trading_bot.auth import init_users_file, get_users, authenticate_user, login_required, admin_required
from trading_bot.ig_api import IGClient
import requests
from div import update_ticker_data_dividend_dates

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'trading_bot_secret_key')
app.config['SESSION_TYPE'] = 'filesystem'
app.config['PERMANENT_SESSION_LIFETIME'] = datetime.timedelta(hours=12)

# Initialize webhook handler
webhook_handler = WebhookHandler()

# Initialize the users file
init_users_file()

@app.route('/')
def index():
    """Root endpoint - redirects to dashboard if logged in, otherwise to login page"""
    if 'user' in session:
        return redirect(url_for('dashboard'))
    else:
        return redirect(url_for('login'))

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "message": "Trading Bot webhook server is running"
    })

@app.route('/webhook', methods=['POST'])
def webhook():
    """Webhook endpoint for TradingView alerts"""
    try:
        # Get request data
        if request.is_json:
            data = request.get_json()
        else:
            data = request.data.decode('utf-8')
        
        # Process the webhook
        result = webhook_handler.process_webhook(data)
        
        return jsonify(result)
        
    except Exception as e:
        logging.error(f"Error in webhook endpoint: {e}")
        return jsonify({
            "status": "error",
            "message": f"Error processing webhook: {str(e)}"
        }), 500

@app.route('/markets/<epic>', methods=['GET'])
def get_market_details(epic):
    """Get market details for a specific epic"""
    try:
        # Get market details from the IG API
        if not webhook_handler.trade_manager.ig_client._ensure_session():
            return jsonify({
                "status": "error",
                "message": "Failed to authenticate with IG API"
            }), 401
            
        # Endpoint URL ve header hazırlama
        base_url = webhook_handler.trade_manager.ig_client.BASE_URL
        market_url = f"{base_url}/markets/{epic}"
        market_headers = webhook_handler.trade_manager.ig_client.headers.copy()
        market_headers['Version'] = '3'  # Version 3 provides more detailed market data
        
        try:
            # API isteği yap
            market_response = webhook_handler.trade_manager.ig_client.session.get(market_url, headers=market_headers)
            
            if market_response.status_code == 200:
                market_data = market_response.json()
                
                # Önemli bilgileri çıkar
                snapshot = market_data.get('snapshot', {})
                dealing_rules = market_data.get('dealingRules', {})
                instrument = market_data.get('instrument', {})
                
                # Daha kapsamlı yanıt oluştur
                result = {
                    "status": "success",
                    "epic": epic,
                    "market_details": {
                        "prices": {
                            "bid": snapshot.get('bid'),
                            "offer": snapshot.get('offer'),
                            "current_price": (snapshot.get('bid', 0) + snapshot.get('offer', 0)) / 2 if snapshot.get('bid') is not None and snapshot.get('offer') is not None else None,
                        },
                        "status": {
                            "market_status": snapshot.get('marketStatus'),
                            "tradeable": snapshot.get('tradeable', False)
                        },
                        "instrument": {
                            "name": instrument.get('name'),
                            "type": instrument.get('type'),
                            "currency": instrument.get('currencies', [{}])[0].get('code') if instrument.get('currencies') else None,
                            "expiry": instrument.get('expiry'),
                            "epic": instrument.get('epic'),
                            "lot_size": instrument.get('lotSize'),
                            "contract_size": instrument.get('contractSize'),
                            "controlled_risk_allowed": instrument.get('controlledRiskAllowed', False),
                            "streaming_prices_available": instrument.get('streamingPricesAvailable', False),
                            "market_id": instrument.get('marketId')
                        },
                        "dealing_rules": {
                            "min_stop_distance": dealing_rules.get('minNormalStopOrLimitDistance', {}).get('value'),
                            "min_stop_distance_unit": dealing_rules.get('minNormalStopOrLimitDistance', {}).get('unit'),
                            "min_deal_size": dealing_rules.get('minDealSize', {}).get('value'),
                            "min_deal_size_unit": dealing_rules.get('minDealSize', {}).get('unit'),
                            "max_deal_size": dealing_rules.get('maxDealSize', {}).get('value'),
                            "max_deal_size_unit": dealing_rules.get('maxDealSize', {}).get('unit')
                        }
                    }
                }
                
                return jsonify(result)
            else:
                error_msg = ""
                try:
                    error_msg = market_response.json().get('errorCode', '')
                except:
                    error_msg = market_response.text
                    
                logging.error(f"Failed to get market details: {market_response.status_code} - {error_msg}")
                return jsonify({
                    "status": "error",
                    "message": f"Failed to get market details for epic: {epic}",
                    "error_code": market_response.status_code,
                    "error_message": error_msg
                }), 404
                
        except Exception as e:
            logging.error(f"Exception while getting market details: {e}")
            return jsonify({
                "status": "error",
                "message": f"Error getting market details: {str(e)}"
            }), 500
            
    except Exception as e:
        logging.error(f"Error getting market details: {e}")
        return jsonify({
            "status": "error",
            "message": f"Error getting market details: {str(e)}"
        }), 500

@app.route('/positions', methods=['GET'])
def get_positions():
    """Get all open positions"""
    try:
        # Get all positions
        result = webhook_handler.trade_manager.get_all_positions()
        return jsonify(result)
        
    except Exception as e:
        logging.error(f"Error getting positions: {e}")
        return jsonify({
            "status": "error",
            "message": f"Error getting positions: {str(e)}"
        }), 500

@app.route('/position/status', methods=['GET'])
def check_position_status():
    """Check the status of a specific position"""
    try:
        # Get query parameters
        deal_reference = request.args.get('reference')
        ticker = request.args.get('ticker')
        
        if not deal_reference and not ticker:
            return jsonify({
                "status": "error",
                "message": "Must provide either 'reference' or 'ticker' parameter"
            }), 400
        
        # Check position status
        result = webhook_handler.trade_manager.check_position_status(
            deal_reference=deal_reference,
            ticker=ticker
        )
        return jsonify(result)
        
    except Exception as e:
        logging.error(f"Error checking position status: {e}")
        return jsonify({
            "status": "error",
            "message": f"Error checking position status: {str(e)}"
        }), 500

@app.route('/position/today', methods=['GET'])
def get_today_trades():
    """Get trades made today"""
    try:
        # Get today's trades from the trade manager
        today_trades = webhook_handler.trade_manager.today_trades
        
        # Format the response
        formatted_trades = {}
        for ticker, trade in today_trades.items():
            formatted_trades[ticker] = {
                "time": trade.get("time").isoformat() if trade.get("time") else None,
                "direction": trade.get("params", {}).get("direction"),
                "entry_price": trade.get("params", {}).get("entry_price"),
                "position_size": trade.get("params", {}).get("position_size"),
                "deal_reference": trade.get("deal_reference"),
                "epic": trade.get("epic")
            }
        
        return jsonify({
            "status": "success",
            "trade_count": len(formatted_trades),
            "trades": formatted_trades
        })
        
    except Exception as e:
        logging.error(f"Error getting today's trades: {e}")
        return jsonify({
            "status": "error",
            "message": f"Error getting today's trades: {str(e)}"
        }), 500

@app.route('/history/transactions', methods=['GET'])
def get_transaction_history():
    """Get transaction history"""
    try:
        # Get query parameters
        days = request.args.get('days', default=7, type=int)
        max_results = request.args.get('max_results', default=50, type=int)
        
        # Get transaction history
        result = webhook_handler.trade_manager.get_transaction_history(
            days=days,
            max_results=max_results
        )
        return jsonify(result)
        
    except Exception as e:
        logging.error(f"Error getting transaction history: {e}")
        return jsonify({
            "status": "error",
            "message": f"Error getting transaction history: {str(e)}"
        }), 500

@app.route('/history/activity', methods=['GET'])
def get_activity_history():
    """Get activity history"""
    try:
        # Get query parameters
        days = request.args.get('days', default=7, type=int)
        max_results = request.args.get('max_results', default=50, type=int)
        
        # Get activity history
        result = webhook_handler.trade_manager.get_activity_history(
            days=days,
            max_results=max_results
        )
        return jsonify(result)
        
    except Exception as e:
        logging.error(f"Error getting activity history: {e}")
        return jsonify({
            "status": "error",
            "message": f"Error getting activity history: {str(e)}"
        }), 500

@app.route('/history/all', methods=['GET'])
def get_all_history():
    """Get comprehensive trading history"""
    try:
        # Get query parameters
        days = request.args.get('days', default=7, type=int)
        max_results = request.args.get('max_results', default=50, type=int)
        
        # Get all history
        result = webhook_handler.trade_manager.get_all_history(
            days=days,
            max_results=max_results
        )
        return jsonify(result)
        
    except Exception as e:
        logging.error(f"Error getting comprehensive history: {e}")
        return jsonify({
            "status": "error",
            "message": f"Error getting comprehensive history: {str(e)}"
        }), 500

@app.route('/test', methods=['GET'])
def test():
    """Test endpoint to verify the bot is working"""
    # Load ticker data to check if CSV is readable
    ticker_data = load_ticker_data()
    ticker_count = len(ticker_data) if not ticker_data.empty else 0
    
    return jsonify({
        "status": "ok",
        "message": "Trading Bot test endpoint",
        "ticker_count": ticker_count
    })

@app.route('/test/epics', methods=['GET'])
def test_epic_data():
    """Test endpoint to check EPIC data in ticker file"""
    try:
        # Ticker data dosyasını kontrol et
        ticker_data = load_ticker_data()
        if ticker_data.empty:
            return jsonify({
                "status": "error",
                "message": "Ticker data file is empty or not found"
            }), 404
        
        # IG EPIC sütunu var mı kontrol et
        has_epic_column = 'IG EPIC' in ticker_data.columns
        
        # Toplam epic sayısını ve geçerli epic sayısını hesapla
        total_rows = len(ticker_data)
        valid_epics = 0
        epic_values = []
        
        if has_epic_column:
            # Geçerli EPIC'leri say ve ilk 20 örneği ekle
            for index, row in ticker_data.iterrows():
                epic = row.get('IG EPIC', '')
                symbol = row.get('Symbol', '')
                
                if epic and epic != '?':
                    valid_epics += 1
                    if len(epic_values) < 20:  # Sadece ilk 20 örneği göster
                        epic_values.append({
                            'symbol': symbol,
                            'epic': epic
                        })
        
        # Sütunların bir listesini hazırla
        columns = list(ticker_data.columns)
        
        # CSV dosyasının ilk 5 satırını örnek olarak al
        sample_data = []
        for i in range(min(5, total_rows)):
            row_data = {}
            for col in columns:
                row_data[col] = ticker_data.iloc[i][col]
            sample_data.append(row_data)
        
        return jsonify({
            "status": "success",
            "ticker_file_info": {
                "total_rows": total_rows,
                "columns": columns,
                "has_epic_column": has_epic_column,
                "valid_epic_count": valid_epics,
                "epic_examples": epic_values,
                "sample_rows": sample_data
            }
        })
        
    except Exception as e:
        logging.error(f"Error in test endpoint: {e}")
        return jsonify({
            "status": "error",
            "message": f"Error in test endpoint: {str(e)}"
        }), 500

@app.route('/markets', methods=['GET'])
def list_markets():
    """Get markets based on filtering criteria"""
    try:
        # Get query parameters
        instrument_type = request.args.get('type', '').lower()  # spreadbet, cfd, etc.
        search_term = request.args.get('search', '')
        max_results = request.args.get('max_results', default=50, type=int)
        
        if not webhook_handler.trade_manager.ig_client._ensure_session():
            return jsonify({
                "status": "error",
                "message": "Failed to authenticate with IG API"
            }), 401
            
        # Ticker data'dan epic bilgilerini al (eğer varsa)
        ticker_data = load_ticker_data()
        known_epics = {}
        
        if not ticker_data.empty and 'IG EPIC' in ticker_data.columns:
            # CSV dosyasındaki EPIC bilgilerini topla
            for index, row in ticker_data.iterrows():
                symbol = row.get('Symbol', '')
                epic = row.get('IG EPIC', '')
                # NaN veya sayısal değer değilse ve boş string değilse işle
                if epic and epic != '?' and isinstance(epic, str):
                    known_epics[epic] = symbol
        
        # Eğer arama terimi varsa, IG API üzerinden arama yap
        markets = []
        filtered_markets = []
        
        if search_term:
            # IG API'nin market arama endpoint'ini kullan
            search_results = webhook_handler.trade_manager.ig_client.search_market(search_term)
            
            if search_results and isinstance(search_results, dict) and 'markets' in search_results:
                markets = search_results['markets']
            elif search_results and isinstance(search_results, list):
                markets = search_results
        
        # Eğer arama yoksa veya bilinen epic'leri kullanacaksak
        if not search_term or not markets:
            # Bilinen sembolleri temel alarak piyasaları ara
            for epic, symbol in known_epics.items():
                # CSV'deki sembollere göre arama yap
                symbol_to_search = symbol.split(':')[-1] if ':' in symbol else symbol
                
                # API üzerinden sembolü ara
                search_results = webhook_handler.trade_manager.ig_client.search_market(symbol_to_search)
                
                if search_results and isinstance(search_results, dict) and 'markets' in search_results:
                    symbol_markets = search_results['markets']
                elif search_results and isinstance(search_results, list):
                    symbol_markets = search_results
                else:
                    symbol_markets = []
                
                if symbol_markets:
                    # Doğru epic'i bulmaya çalış
                    found = False
                    for market in symbol_markets:
                        market_epic = market.get('epic', '')
                        # CSV'deki epic ile aynı mı kontrol et
                        if market_epic == epic:
                            markets.append(market)
                            found = True
                            break
                    
                    # Hiç eşleşme bulunamadıysa ilk sonucu kullan
                    if not found and symbol_markets:
                        markets.append(symbol_markets[0])
        
        logging.info(f"Found {len(markets)} markets before filtering")
        
        # Spreadbet türüne göre filtrele
        if instrument_type == 'spreadbet':
            for market in markets:
                epic = market.get('epic', '')
                
                # Epic değeri string olmayabilir, kontrol et
                if not isinstance(epic, str):
                    logging.warning(f"Non-string EPIC value found: {epic}, type: {type(epic)}")
                    epic = str(epic) if epic is not None else ""
                
                instrument_type_value = market.get('instrumentType', '')
                if not isinstance(instrument_type_value, str):
                    instrument_type_value = str(instrument_type_value) if instrument_type_value is not None else ""
                instrument_type_value = instrument_type_value.lower()
                
                # IG'nin EPIC isimlendirme formatına göre spreadbet tespiti
                is_spreadbet = False
                
                # Önce API'nin döndüğü instrumentType'a bak
                if 'spreadbet' in instrument_type_value:
                    is_spreadbet = True
                # EPIC formatına göre kontrol et (eğer epic string ise)
                elif isinstance(epic, str) and epic:
                    # Prefix kontrolü
                    has_prefix = any(epic.startswith(prefix) for prefix in 
                                    ['CS.D.', 'IX.D.', 'KA.D.', 'UA.D.', 'UD.D.', 'UK.D.', 'UP.D.'] 
                                    if isinstance(epic, str))
                    
                    # Suffix kontrolü
                    has_suffix = False
                    if isinstance(epic, str):
                        has_suffix = '.DAILY.IP' in epic or '.CASH.IP' in epic
                    
                    is_spreadbet = has_prefix or has_suffix
                    
                if is_spreadbet:
                    # Spreadbet olarak işaretle
                    market['instrumentType'] = 'SPREADBET'
                    filtered_markets.append(market)
                    
                    logging.info(f"Found spreadbet market: {epic}")
                    
                    if len(filtered_markets) >= max_results:
                        break
                else:
                    logging.debug(f"Skipping non-spreadbet market: {epic}, type: {instrument_type_value}")
        else:
            # Spreadbet olmayan filtreleme mantığı
            filtered_markets = markets[:max_results]
        
        # Sonuçları daha ayrıntılı düzenle
        results = []
        for market in filtered_markets:
            # Her alanı güvenli şekilde işle
            epic = market.get('epic', '')
            if not isinstance(epic, str):
                epic = str(epic) if epic is not None else ""
                
            instrument_type_value = market.get('instrumentType', '')
            if not isinstance(instrument_type_value, str):
                instrument_type_value = str(instrument_type_value) if instrument_type_value is not None else ""
            
            # Güvenli bir spreadbet_compatible hesapla
            spreadbet_compatible = False
            
            # instrumentType kontrolü
            if isinstance(instrument_type_value, str) and 'SPREADBET' in instrument_type_value.upper():
                spreadbet_compatible = True
            # EPIC prefix kontrolü
            elif isinstance(epic, str) and epic:
                if any(epic.startswith(prefix) for prefix in 
                      ['CS.D.', 'IX.D.', 'KA.D.', 'UA.D.', 'UD.D.', 'UK.D.', 'UP.D.']):
                    spreadbet_compatible = True
                # EPIC suffix kontrolü
                elif '.DAILY.IP' in epic or '.CASH.IP' in epic:
                    spreadbet_compatible = True
            
            results.append({
                'epic': epic,
                'name': str(market.get('instrumentName', '')),
                'symbol': str(market.get('marketId', '')),
                'instrumentType': instrument_type_value,
                'expiry': str(market.get('expiry', '')),
                'spreadbet_compatible': spreadbet_compatible
            })
        
        return jsonify({
            "status": "success",
            "filter_type": instrument_type or "none",
            "search_term": search_term or "none",
            "count": len(results),
            "markets": results
        })
        
    except Exception as e:
        logging.error(f"Error listing markets: {e}")
        # Detaylı hata izleme için stack trace
        import traceback
        stack_trace = traceback.format_exc()
        logging.error(f"Stack trace: {stack_trace}")
        
        return jsonify({
            "status": "error",
            "message": f"Error listing markets: {str(e)}",
            "traceback": stack_trace
        }), 500

@app.route('/markets/spreadbet', methods=['GET'])
def list_spreadbet_markets():
    """Get all spreadbet markets available in the ticker data"""
    try:
        # CSV dosyasından ticker verilerini yükle
        ticker_data = load_ticker_data()
        if ticker_data.empty:
            return jsonify({
                "status": "error",
                "message": "Ticker data file is empty or not found"
            }), 404
        
        # IG API oturumunu kontrol et
        if not webhook_handler.trade_manager.ig_client._ensure_session():
            return jsonify({
                "status": "error",
                "message": "Failed to authenticate with IG API"
            }), 401
        
        # CSV dosyasından EPIC bilgilerini topla
        epics_to_check = []
        epic_to_symbol_map = {}
        
        if 'IG EPIC' in ticker_data.columns:
            for index, row in ticker_data.iterrows():
                try:
                    symbol = row.get('Symbol', '')
                    epic = row.get('IG EPIC', '')
                    
                    # EPIC değeri string mi kontrol et
                    if not isinstance(epic, str):
                        if epic is None or pd.isna(epic):
                            continue
                        epic = str(epic)
                    
                    # Boş veya geçersiz değerleri atla
                    if not epic or epic == '?':
                        continue
                        
                    epics_to_check.append(epic)
                    epic_to_symbol_map[epic] = symbol
                    
                except Exception as row_error:
                    logging.warning(f"Error processing row {index}: {row_error}")
                    continue
        
        logging.info(f"Found {len(epics_to_check)} EPICs to check in ticker data")
        
        # Spreadbet türündeki piyasaları bul
        spreadbet_markets = []
        error_markets = []
        
        for epic in epics_to_check:
            try:
                # EPIC değeri string mi tekrar kontrol et
                if not isinstance(epic, str):
                    logging.warning(f"Non-string EPIC encountered: {epic}, type: {type(epic)}")
                    continue
                
                logging.info(f"Checking market details for EPIC: {epic}")
                
                # Market detaylarını çek
                market_details = webhook_handler.trade_manager.ig_client._get_market_details(epic)
                
                if not market_details:
                    logging.warning(f"No market details found for EPIC: {epic}")
                    continue
                
                # Instrument bilgisini kontrol et
                instrument = market_details.get('instrument', {})
                if not instrument:
                    logging.warning(f"No instrument data for EPIC: {epic}")
                    continue
                
                # Instrument type'ı al
                instrument_type = instrument.get('type', '')
                if not isinstance(instrument_type, str):
                    instrument_type = str(instrument_type) if instrument_type is not None else ""
                instrument_type = instrument_type.lower()
                
                # Spreadbet olup olmadığını kontrol et
                is_spreadbet = 'spreadbet' in instrument_type
                
                if is_spreadbet:
                    spreadbet_markets.append({
                        'epic': epic,
                        'symbol': epic_to_symbol_map.get(epic, ''),
                        'instrumentType': instrument_type,
                        'name': instrument.get('name', ''),
                        'controlledRiskAllowed': bool(instrument.get('controlledRiskAllowed', False)),
                        'currency': market_details.get('currency', ''),
                        'market_status': market_details.get('market_status', '')
                    })
                    logging.info(f"Found spreadbet market: {epic}")
                else:
                    logging.debug(f"Skipping non-spreadbet market: {epic} with type: {instrument_type}")
                
                # API'yi çok hızlı sorgulamaktan kaçınmak için kısa bir bekleme
                time.sleep(0.1)
                
            except Exception as e:
                logging.warning(f"Error checking EPIC {epic}: {e}")
                error_markets.append({
                    'epic': epic,
                    'symbol': epic_to_symbol_map.get(epic, ''),
                    'error': str(e)
                })
                continue
        
        return jsonify({
            "status": "success",
            "count": len(spreadbet_markets),
            "markets": spreadbet_markets,
            "errors": error_markets
        })
        
    except Exception as e:
        # Detaylı hata izleme
        import traceback
        stack_trace = traceback.format_exc()
        logging.error(f"Error listing spreadbet markets: {e}")
        logging.error(f"Stack trace: {stack_trace}")
        
        return jsonify({
            "status": "error",
            "message": f"Error listing spreadbet markets: {str(e)}",
            "traceback": stack_trace
        }), 500

@app.route('/test/instrument/<epic>', methods=['GET'])
def test_instrument_details(epic):
    """Test endpoint to get instrument details for a specific EPIC"""
    try:
        # IG API oturumunu kontrol et
        if not webhook_handler.trade_manager.ig_client._ensure_session():
            return jsonify({
                "status": "error",
                "message": "Failed to authenticate with IG API"
            }), 401
            
        # Endpoint URL ve header hazırlama
        base_url = webhook_handler.trade_manager.ig_client.BASE_URL
        market_url = f"{base_url}/markets/{epic}"
        market_headers = webhook_handler.trade_manager.ig_client.headers.copy()
        market_headers['Version'] = '3'  # Version 3 provides more detailed market data
        
        try:
            # API isteği yap
            logging.info(f"Requesting market details for EPIC: {epic}")
            market_response = webhook_handler.trade_manager.ig_client.session.get(market_url, headers=market_headers)
            
            # Tam API yanıtını göster
            logging.info(f"Response status: {market_response.status_code}")
            
            raw_response = None
            if market_response.status_code == 200:
                raw_response = market_response.json()
                
                # Log instrument type
                instrument_type = raw_response.get('instrument', {}).get('type', 'UNKNOWN')
                logging.info(f"Instrument type for {epic}: {instrument_type}")
                
                # Check if it's a spreadbet
                is_spreadbet = 'SPREADBET' in instrument_type.upper()
                logging.info(f"Is spreadbet: {is_spreadbet}")
                
                # Tüm yanıtı döndür
                return jsonify({
                    "status": "success",
                    "epic": epic,
                    "instrument_type": instrument_type,
                    "is_spreadbet": is_spreadbet,
                    "raw_api_response": raw_response
                })
            else:
                error_msg = ""
                try:
                    error_content = market_response.json()
                    error_msg = error_content.get('errorCode', '') or json.dumps(error_content)
                except:
                    error_msg = market_response.text
                    
                logging.error(f"API error for {epic}: {market_response.status_code} - {error_msg}")
                return jsonify({
                    "status": "error",
                    "message": f"API error: {market_response.status_code}",
                    "error_details": error_msg,
                    "epic": epic,
                    "raw_response": raw_response or market_response.text
                }), market_response.status_code
                
        except Exception as e:
            logging.error(f"Exception getting market details for {epic}: {e}")
            return jsonify({
                "status": "error",
                "message": f"Exception: {str(e)}",
                "epic": epic
            }), 500
            
    except Exception as e:
        logging.error(f"Error in test endpoint: {e}")
        return jsonify({
            "status": "error",
            "message": f"Error in test endpoint: {str(e)}"
        }), 500

@app.route('/epic/lookup', methods=['GET'])
def lookup_epic():
    """Sembolden (işlem çifti) EPIC kodunu bulan endpoint"""
    try:
        # Get query parameters
        symbol = request.args.get('symbol', '')
        
        if not symbol:
            return jsonify({
                "status": "error",
                "message": "Symbol parameter is required"
            }), 400
            
        logging.info(f"Looking up EPIC for symbol: {symbol}")
        
        # IG API oturumunu kontrol et
        if not webhook_handler.trade_manager.ig_client._ensure_session():
            return jsonify({
                "status": "error",
                "message": "Failed to authenticate with IG API"
            }), 401
        
        # Önce ticker data dosyasında bu sembole karşılık gelen EPIC kodu var mı kontrol et
        ticker_data = load_ticker_data()
        csv_epic = None
        
        if not ticker_data.empty and 'Symbol' in ticker_data.columns and 'IG EPIC' in ticker_data.columns:
            # Sembol ile eşleşen satırı bul
            for index, row in ticker_data.iterrows():
                csv_symbol = str(row.get('Symbol', ''))
                if csv_symbol.lower() == symbol.lower():
                    epic_value = row.get('IG EPIC')
                    if epic_value and epic_value != '?' and not pd.isna(epic_value):
                        csv_epic = str(epic_value)
                        logging.info(f"Found EPIC in CSV: {csv_epic} for symbol {symbol}")
                        break
        
        # IG API'den EPIC kodunu ara
        api_epic = webhook_handler.trade_manager.ig_client.get_epic_from_symbol(symbol)
        
        # Eğer API'den EPIC kodu alındıysa, bu değeri kullan
        found_epic = api_epic if api_epic else csv_epic
        
        if not found_epic:
            return jsonify({
                "status": "error",
                "message": f"No EPIC found for symbol: {symbol}"
            }), 404
            
        # EPIC'in detaylarını al (instrument type vb.)
        epic_details = None
        instrument_type = "UNKNOWN"
        is_spreadbet = False
        controlled_risk_allowed = False
        
        try:
            # Market detaylarını çek
            market_details = webhook_handler.trade_manager.ig_client._get_market_details(found_epic)
            
            if market_details and 'instrument' in market_details:
                instrument = market_details.get('instrument', {})
                instrument_type = str(instrument.get('type', 'UNKNOWN'))
                is_spreadbet = 'SPREADBET' in instrument_type.upper()
                controlled_risk_allowed = bool(instrument.get('controlledRiskAllowed', False))
                
                epic_details = {
                    'name': str(instrument.get('name', '')),
                    'currency': market_details.get('currency', ''),
                    'market_status': market_details.get('market_status', ''),
                    'bid': market_details.get('bid'),
                    'offer': market_details.get('offer'),
                    'min_stop_distance': market_details.get('min_stop_distance'),
                    'min_limit_distance': market_details.get('min_limit_distance')
                }
        except Exception as e:
            logging.warning(f"Could not get market details for {found_epic}: {e}")
            # Detayları alamazsa işleme devam et ama uyarı ver
        
        # Yanıtı oluştur
        result = {
            "status": "success",
            "symbol": symbol,
            "epic": found_epic,
            "source": "API" if api_epic else "CSV" if csv_epic else "UNKNOWN",
            "instrument_type": instrument_type,
            "is_spreadbet": is_spreadbet,
            "controlled_risk_allowed": controlled_risk_allowed
        }
        
        # Eğer EPIC detayları alınabildiyse ekle
        if epic_details:
            result["epic_details"] = epic_details
            
        return jsonify(result)
        
    except Exception as e:
        # Detaylı hata izleme
        import traceback
        stack_trace = traceback.format_exc()
        logging.error(f"Error looking up EPIC: {e}")
        logging.error(f"Stack trace: {stack_trace}")
        
        return jsonify({
            "status": "error",
            "message": f"Error looking up EPIC: {str(e)}",
            "traceback": stack_trace
        }), 500

# Dashboard routes

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page for the dashboard"""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # Authenticate user
        authenticated, role = authenticate_user(username, password)
        
        if authenticated:
            # Set session variables
            session['user'] = username
            session['role'] = role
            
            # Redirect to the dashboard or saved next_url
            next_url = session.pop('next_url', url_for('dashboard'))
            flash(f'Welcome back, {username}!', 'success')
            return redirect(next_url)
        else:
            flash('Invalid username or password', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    """Logout user and clear session"""
    if 'user' in session:
        user = session.pop('user')
        session.clear()
        flash(f'You have been logged out, {user}', 'info')
    
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    """Main dashboard page"""
    # Get API connection status
    ig_connected = webhook_handler.trade_manager.ig_client._ensure_session()
    
    # Get open positions
    positions_response = webhook_handler.trade_manager.get_all_positions()
    open_positions = len(positions_response.get('positions', [])) if positions_response.get('status') == 'success' else 0
    
    # Get working orders - fixing the missing method issue
    try:
        # Try to get working orders using IG client directly
        orders_response = webhook_handler.trade_manager.ig_client.get_working_orders()
        working_orders = len(orders_response.get('workingOrders', [])) if isinstance(orders_response, dict) else 0
    except Exception as e:
        logging.error(f"Error getting working orders: {e}")
        working_orders = 0
    
    # Get today's trades
    today_trades = len(webhook_handler.trade_manager.today_trades)
    
    # Get recent trades
    recent_trades = []
    try:
        history_response = webhook_handler.trade_manager.get_transaction_history(days=7, max_results=10)
        if history_response.get('status') == 'success':
            for trade in history_response.get('transactions', []):
                status = trade.get('status', 'UNKNOWN')
                status_color = {
                    'OPEN': 'success',
                    'CLOSED': 'secondary',
                    'DELETED': 'danger',
                    'REJECTED': 'warning'
                }.get(status, 'info')
                
                recent_trades.append({
                    'time': trade.get('date', ''),
                    'symbol': trade.get('instrumentName', ''),
                    'direction': trade.get('direction', ''),
                    'price': trade.get('openLevel', 0),
                    'size': trade.get('size', 0),
                    'status': status,
                    'status_color': status_color,
                    'reference': trade.get('dealReference', '')
                })
    except Exception as e:
        logging.error(f"Error getting recent trades: {e}")
    
    # Get system resources
    try:
        memory_usage = f"{psutil.virtual_memory().percent}%"
        cpu_usage = f"{psutil.cpu_percent()}%"
        disk_usage = f"{psutil.disk_usage('/').percent}%"
        
        # Calculate uptime
        uptime_seconds = time.time() - psutil.boot_time()
        days, remainder = divmod(uptime_seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, _ = divmod(remainder, 60)
        uptime = f"{int(days)} days, {int(hours)} hours, {int(minutes)} minutes"
    except Exception as e:
        logging.error(f"Error getting system resources: {e}")
        memory_usage = "N/A"
        cpu_usage = "N/A"
        disk_usage = "N/A"
        uptime = "N/A"
    
    # Get activity data for the chart
    activity_dates = []
    activity_counts = []
    try:
        # Get the last 7 days
        for i in range(6, -1, -1):
            date = (datetime.datetime.now() - datetime.timedelta(days=i)).strftime('%Y-%m-%d')
            activity_dates.append(date)
            
            # Count trades for this day
            count = 0
            for trade in webhook_handler.trade_manager.today_trades.values():
                trade_date = trade.get('time', datetime.datetime.now()).strftime('%Y-%m-%d')
                if trade_date == date:
                    count += 1
            activity_counts.append(count)
    except Exception as e:
        logging.error(f"Error calculating activity data: {e}")
        activity_dates = [day for day in ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']]
        activity_counts = [0, 0, 0, 0, 0, 0, 0]
    
    return render_template('dashboard.html',
                          ig_connected=ig_connected,
                          open_positions=open_positions,
                          working_orders=working_orders,
                          today_trades=today_trades,
                          recent_trades=recent_trades,
                          memory_usage=memory_usage,
                          cpu_usage=cpu_usage,
                          disk_usage=disk_usage,
                          uptime=uptime,
                          activity_dates=activity_dates,
                          activity_counts=activity_counts)

@app.route('/dashboard/positions')
@login_required
def dashboard_positions():
    """Positions management page"""
    # Get all open positions
    positions_response = webhook_handler.trade_manager.get_all_positions()
    positions = positions_response.get('positions', []) if positions_response.get('status') == 'success' else []
    
    # Calculate profit for each position if it's missing
    for position in positions:
        # Format profit levels if missing
        if position.get('limitLevel') is None and position.get('profitLevel') is not None:
            position['limitLevel'] = position['profitLevel']
            
        # Calculate profit if missing
        if position.get('profit') is None:
            direction = position.get('direction')
            level = float(position.get('level', 0))
            size = float(position.get('size', 0))
            
            if direction == 'BUY' and position.get('offer') is not None:
                # For BUY positions, profit = (current_offer - open_level) * size
                current_price = float(position.get('offer', 0))
                position['profit'] = round((current_price - level) * size, 2)
            elif direction == 'SELL' and position.get('bid') is not None:
                # For SELL positions, profit = (open_level - current_bid) * size
                current_price = float(position.get('bid', 0))
                position['profit'] = round((level - current_price) * size, 2)
    
    # Log positions
    logging.info(f"Positions data: {json.dumps(positions)}")
    
    # Get working orders directly from the IG API
    try:
        # Try to get working orders using IG client directly
        orders = webhook_handler.trade_manager.ig_client.get_working_orders()
        
        # Fix order types and empty values
        for order in orders:
            if not order.get('orderType'):
                order['orderType'] = 'LIMIT'  # Default type
            
            # Make sure size has a value
            if not order.get('size'):
                # Default size based on epic
                epic = order.get('epic', '')
                if 'SP.' in epic or any(prefix in epic for prefix in ['KA.D.', 'CS.D.']):
                    order['size'] = '1.0'  # Default size for smaller instruments
                else:
                    order['size'] = '0.5'  # Default size for others
            
            # Set level if missing
            if not order.get('level') and order.get('stopLevel'):
                # Calculate a reasonable level based on stop level
                stop_level = float(order['stopLevel']) if order['stopLevel'] else 0
                if order.get('direction') == 'BUY':
                    order['level'] = str(round(stop_level * 0.95, 2))  # 5% below stop
                else:
                    order['level'] = str(round(stop_level * 1.05, 2))  # 5% above stop
        
        # Log orders
        logging.info(f"Orders data: {json.dumps(orders)}")
        
    except Exception as e:
        logging.error(f"Error getting working orders: {e}")
        orders = []
    
    return render_template('positions.html', positions=positions, orders=orders)

@app.route('/dashboard/settings')
@login_required
def dashboard_settings():
    """Settings management page"""
    # Load ticker data
    ticker_data = load_ticker_data()
    
    # Load settings from JSON file
    settings_path = os.path.join(os.path.dirname(__file__), 'settings.json')
    try:
        with open(settings_path, 'r') as f:
            settings = json.load(f)
    except Exception as e:
        logging.error(f"Error loading settings: {e}")
        settings = {
            "api": {
                "ig_username": "",
                "ig_password": "",
                "ig_api_key": "",
                "ig_account_type": "DEMO"
            },
            "trading": {
                "max_open_positions": 10,
                "alert_max_age_seconds": 5,
                "csv_file_path": "ticker_data.csv"
            },
            "validation": {
                "check_same_day_trades": True,
                "check_open_position_limit": True,
                "check_existing_position": True,
                "check_alert_timestamp": True,
                "check_dividend_date": True
            }
        }
    
    # Get API credentials from settings
    ig_username = settings['api'].get('ig_username', '')
    ig_password = settings['api'].get('ig_password', '')
    ig_api_key = settings['api'].get('ig_api_key', '')
    ig_demo = settings['api'].get('ig_account_type', 'DEMO') == 'DEMO'
    
    # Check if connected to IG API
    ig_connected = False
    if hasattr(webhook_handler, 'trade_manager') and hasattr(webhook_handler.trade_manager, 'ig_client'):
        ig_connected = webhook_handler.trade_manager.ig_client.is_connected()
    
    # Get webhook settings
    webhook_url = request.host_url + 'webhook'
    
    return render_template('settings.html',
                          ticker_data=ticker_data,
                          ticker_count=len(ticker_data) if not ticker_data.empty else 0,
                          ig_username=ig_username,
                          ig_password='*' * len(ig_password) if ig_password else '',
                          ig_api_key='*' * len(ig_api_key) if ig_api_key else '',
                          ig_demo=ig_demo,
                          ig_connected=ig_connected,
                          webhook_url=webhook_url,
                          validation=settings['validation'],
                          trading=settings['trading'])

@app.route('/dashboard/logs')
@login_required
def dashboard_logs():
    """Logs viewing page"""
    # Get log files
    log_files = []
    log_directory = os.environ.get('LOG_DIRECTORY', '.')
    
    try:
        for file in os.listdir(log_directory):
            if file.endswith('.log'):
                file_path = os.path.join(log_directory, file)
                file_size = os.path.getsize(file_path)
                file_mtime = os.path.getmtime(file_path)
                
                # Get the last few lines of the log file
                try:
                    with open(file_path, 'r') as f:
                        lines = f.readlines()
                        preview = ''.join(lines[-5:]) if lines else "Log file is empty"
                except Exception as e:
                    preview = f"Error reading log file: {e}"
                
                log_files.append({
                    'name': file,
                    'path': file_path,
                    'size': file_size,
                    'modified': datetime.datetime.fromtimestamp(file_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                    'preview': preview
                })
    except Exception as e:
        logging.error(f"Error reading log directory: {e}")
    
    return render_template('logs.html', log_files=log_files)

@app.route('/view/log/<path:filename>')
@login_required
def view_log(filename):
    """View a specific log file"""
    log_directory = os.environ.get('LOG_DIRECTORY', '.')
    file_path = os.path.join(log_directory, filename)
    
    # Security check to prevent directory traversal
    if not os.path.exists(file_path) or '..' in filename:
        flash('Log file not found', 'danger')
        return redirect(url_for('dashboard_logs'))
    
    try:
        with open(file_path, 'r') as f:
            content = f.read()
    except Exception as e:
        flash(f'Error reading log file: {e}', 'danger')
        content = ''
    
    return render_template('view_log.html', filename=filename, content=content)

@app.route('/view/trade/<reference>')
@login_required
def view_trade(reference):
    """View details for a specific trade"""
    # Get position status
    trade_details = webhook_handler.trade_manager.check_position_status(deal_reference=reference)
    
    return render_template('view_trade.html', trade=trade_details, reference=reference)

@app.route('/test/webhook', methods=['GET', 'POST'])
@login_required
def test_webhook():
    """Test webhook endpoint with a form interface"""
    if request.method == 'POST':
        webhook_url = request.form.get('webhook_url', '')
        alert_data = request.form.get('alert_data', '')
        
        # Send test webhook
        try:
            response = requests.post(
                webhook_url,
                json={"message": alert_data, "test_mode": True},
                headers={"Content-Type": "application/json"}
            )
            
            return render_template(
                'test_webhook.html',
                webhook_url=webhook_url,
                alert_data=alert_data,
                response=response.text
            )
            
        except Exception as e:
            flash(f"Error sending webhook: {str(e)}", "error")
            return render_template(
                'test_webhook.html',
                webhook_url=webhook_url,
                alert_data=alert_data,
                response=str(e)
            )
    
    # Default values for GET request
    default_url = request.url_root + "webhook"
    default_data = "ASX_DLY:IAG UP 8.05 0.08 0.101 0.121 0.139 0.153 0.163 0.17 0.175 0.178 0.181"
    
    return render_template(
        'test_webhook.html',
        webhook_url=default_url,
        alert_data=default_data
    )

@app.route('/api/docs')
@login_required
def api_docs():
    """API documentation page"""
    # Set the base URL for API docs
    base_url = request.host
    
    return render_template('api_docs.html', base_url=base_url)

@app.route('/admin/panel')
@admin_required
def admin_panel():
    """Admin panel for user management"""
    users = get_users()
    
    return render_template('admin_panel.html', users=users)

@app.route('/admin/users/add', methods=['POST'])
@admin_required
def add_user():
    """Add a new user"""
    username = request.form.get('username')
    password = request.form.get('password')
    role = request.form.get('role', 'user')
    
    if not username or not password:
        flash('Username and password are required', 'danger')
        return redirect(url_for('admin_panel'))
    
    # Load existing users
    users = get_users()
    
    # Check if username already exists
    if username in users:
        flash(f'User "{username}" already exists', 'warning')
        return redirect(url_for('admin_panel'))
    
    # Add new user
    users[username] = {
        'password': password,
        'role': role
    }
    
    # Save users back to file
    try:
        # Import USERS_FILE from auth module
        from trading_bot.auth import USERS_FILE
        with open(USERS_FILE, 'w') as f:
            json.dump(users, f, indent=4)
        flash(f'User "{username}" added successfully', 'success')
    except Exception as e:
        flash(f'Error adding user: {e}', 'danger')
    
    return redirect(url_for('admin_panel'))

@app.route('/admin/users/delete/<username>')
@admin_required
def delete_user(username):
    """Delete a user"""
    if username == session.get('user'):
        flash('You cannot delete your own account', 'danger')
        return redirect(url_for('admin_panel'))
    
    # Load existing users
    users = get_users()
    
    # Check if user exists
    if username not in users:
        flash(f'User "{username}" not found', 'warning')
        return redirect(url_for('admin_panel'))
    
    # Delete user
    del users[username]
    
    # Save users back to file
    try:
        # Import USERS_FILE from auth module
        from trading_bot.auth import USERS_FILE
        with open(USERS_FILE, 'w') as f:
            json.dump(users, f, indent=4)
        flash(f'User "{username}" deleted successfully', 'success')
    except Exception as e:
        flash(f'Error deleting user: {e}', 'danger')
    
    return redirect(url_for('admin_panel'))

@app.route('/admin/users/change-password', methods=['POST'])
@admin_required
def change_password():
    """Change a user's password"""
    username = request.form.get('username')
    password = request.form.get('password')
    
    if not username or not password:
        flash('Username and password are required', 'danger')
        return redirect(url_for('admin_panel'))
    
    # Load existing users
    users = get_users()
    
    # Check if user exists
    if username not in users:
        flash(f'User "{username}" not found', 'warning')
        return redirect(url_for('admin_panel'))
    
    # Update password
    users[username]['password'] = password
    
    # Save users back to file
    try:
        # Import USERS_FILE from auth module
        from trading_bot.auth import USERS_FILE
        with open(USERS_FILE, 'w') as f:
            json.dump(users, f, indent=4)
        flash(f'Password for "{username}" changed successfully', 'success')
    except Exception as e:
        flash(f'Error changing password: {e}', 'danger')
    
    return redirect(url_for('admin_panel'))

@app.route('/api/test_connection', methods=['GET'])
@login_required
def test_connection():
    """Test connection to IG API"""
    try:
        # Attempt to login to IG API
        success = webhook_handler.trade_manager.ig_client.login()
        
        if success:
            return jsonify({
                'status': 'success',
                'message': 'Successfully connected to IG API'
            })
        else:
            return jsonify({
                'status': 'error',
                'message': 'Failed to connect to IG API. Please check your credentials.'
            })
    except Exception as e:
        logging.error(f"Error testing IG API connection: {e}")
        return jsonify({
            'status': 'error',
            'message': f'Error: {str(e)}'
        })

@app.route('/api/save_settings', methods=['POST'])
@login_required
def save_settings():
    """Save IG API settings"""
    try:
        data = request.json
        
        if not data:
            return jsonify({
                'status': 'error',
                'message': 'No data provided'
            })
        
        # Extract settings
        username = data.get('username')
        password = data.get('password')
        api_key = data.get('api_key')
        demo = data.get('demo', False)
        
        # Validate settings
        if not username or not password or not api_key:
            return jsonify({
                'status': 'error',
                'message': 'Username, password and API key are required'
            })
        
        # Load settings from JSON file
        settings_path = os.path.join(os.path.dirname(__file__), 'settings.json')
        try:
            with open(settings_path, 'r') as f:
                settings = json.load(f)
        except Exception:
            settings = {
                "api": {},
                "trading": {},
                "validation": {}
            }
        
        # Update API settings
        settings['api']['ig_username'] = username
        settings['api']['ig_password'] = password
        settings['api']['ig_api_key'] = api_key
        settings['api']['ig_account_type'] = "DEMO" if demo else "LIVE"
        
        # Save settings to JSON file
        with open(settings_path, 'w') as f:
            json.dump(settings, f, indent=4)
        
        # Update environment variables
        os.environ['IG_USERNAME'] = username
        os.environ['IG_PASSWORD'] = password
        os.environ['IG_API_KEY'] = api_key
        os.environ['IG_DEMO'] = '1' if demo else '0'
        
        # Create a .env file to persist settings
        env_file_path = os.path.join(os.path.dirname(__file__), '.env')
        
        with open(env_file_path, 'w') as f:
            f.write(f"IG_USERNAME={username}\n")
            f.write(f"IG_PASSWORD={password}\n")
            f.write(f"IG_API_KEY={api_key}\n")
            f.write(f"IG_DEMO={'1' if demo else '0'}\n")
        
        # Reset IG client to use new settings
        webhook_handler.trade_manager.ig_client = IGClient()
        
        return jsonify({
            'status': 'success',
            'message': 'Settings saved successfully'
        })
    except Exception as e:
        logging.error(f"Error saving settings: {e}")
        return jsonify({
            'status': 'error',
            'message': f'Error: {str(e)}'
        })

@app.route('/api/save_validation_rules', methods=['POST'])
@login_required
def save_validation_rules():
    """Save validation rules and trading settings"""
    try:
        data = request.json
        
        if not data:
            return jsonify({
                'status': 'error',
                'message': 'No data provided'
            })
        
        # Extract validation rules
        validation = data.get('validation', {})
        trading = data.get('trading', {})
        
        # Load settings from JSON file
        settings_path = os.path.join(os.path.dirname(__file__), 'settings.json')
        try:
            with open(settings_path, 'r') as f:
                settings = json.load(f)
        except Exception:
            settings = {
                "api": {},
                "trading": {},
                "validation": {}
            }
        
        # Update validation rules
        if validation:
            settings['validation'] = {
                'check_existing_position': validation.get('check_existing_position', True),
                'check_same_day_trades': validation.get('check_same_day_trades', True),
                'check_open_position_limit': validation.get('check_open_position_limit', True),
                'check_alert_timestamp': validation.get('check_alert_timestamp', True),
                'check_dividend_date': validation.get('check_dividend_date', True),
                'check_max_deal_age': validation.get('check_max_deal_age', True),
                'check_total_positions_and_orders': validation.get('check_total_positions_and_orders', True)
            }
        
        # Update trading settings
        if trading:
            settings['trading']['max_open_positions'] = trading.get('max_open_positions', 10)
            settings['trading']['alert_max_age_seconds'] = trading.get('alert_max_age_seconds', 5)
            settings['trading']['max_deal_age_minutes'] = trading.get('max_deal_age_minutes', 60)
            settings['trading']['max_total_positions_and_orders'] = trading.get('max_total_positions_and_orders', 10)
        
        # Save settings to JSON file
        with open(settings_path, 'w') as f:
            json.dump(settings, f, indent=4)
        
        # Update webhook handler with new settings
        if hasattr(webhook_handler, 'update_settings'):
            webhook_handler.update_settings(settings)
        
        return jsonify({
            'status': 'success',
            'message': 'Validation rules saved successfully'
        })
    except Exception as e:
        logging.error(f"Error saving validation rules: {e}")
        return jsonify({
            'status': 'error',
            'message': f'Error: {str(e)}'
        })

@app.route('/api/upload_ticker_data', methods=['POST'])
@login_required
def upload_ticker_data():
    """Upload new ticker data CSV file"""
    try:
        if 'file' not in request.files:
            return jsonify({
                'status': 'error',
                'message': 'No file provided'
            })
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({
                'status': 'error',
                'message': 'No file selected'
            })
            
        if not file.filename.endswith('.csv'):
            return jsonify({
                'status': 'error',
                'message': 'File must be a CSV file'
            })
        
        # Save the file
        try:
            ticker_data_path = os.path.join(os.path.dirname(__file__), 'ticker_data.csv')
            file.save(ticker_data_path)
            
            # Validate the file format
            try:
                df = pd.read_csv(ticker_data_path)
                required_columns = ['Symbol', 'IG EPIC', 'ATR Stop Loss Period', 'ATR Stop Loss Multiple', 
                                   'ATR Profit Target Period', 'ATR Profit Multiple', 'Postion Size Max GBP']
                
                missing_columns = [col for col in required_columns if col not in df.columns]
                
                if missing_columns:
                    return jsonify({
                        'status': 'error',
                        'message': f'CSV file is missing required columns: {", ".join(missing_columns)}'
                    })
                
                return jsonify({
                    'status': 'success',
                    'message': f'Successfully uploaded ticker data with {len(df)} instruments'
                })
                
            except Exception as e:
                return jsonify({
                    'status': 'error',
                    'message': f'Error validating CSV file: {str(e)}'
                })
                
        except Exception as e:
            return jsonify({
                'status': 'error',
                'message': f'Error saving file: {str(e)}'
            })
            
    except Exception as e:
        logging.error(f"Error uploading ticker data: {e}")
        return jsonify({
            'status': 'error',
            'message': f'Error: {str(e)}'
        })

@app.route('/orders', methods=['GET'])
def get_orders():
    """Get all working orders"""
    try:
        # Get all working orders
        orders_response = webhook_handler.trade_manager.ig_client.get_working_orders()
        
        if not orders_response or not isinstance(orders_response, dict):
            return jsonify({
                "status": "error",
                "message": "Failed to get working orders from IG Markets"
            }), 500
            
        orders = orders_response.get('workingOrders', [])
        
        # Format the orders in a more readable way
        formatted_orders = []
        for order in orders:
            # Elde edilen veri yapısını düzgün şekilde işliyoruz
            working_order_data = order.get('workingOrderData', {})
            market_data = order.get('marketData', {})
            
            formatted_orders.append({
                "dealId": working_order_data.get('dealId'),
                "epic": market_data.get('epic'),
                "instrumentName": market_data.get('instrumentName'),
                "direction": working_order_data.get('direction'),
                "size": working_order_data.get('size'),
                "level": working_order_data.get('level'),
                "orderType": working_order_data.get('orderType'),
                "createdDate": working_order_data.get('createdDate'),
                "currencyCode": working_order_data.get('currencyCode'),
                "timeInForce": working_order_data.get('timeInForce'),
                "marketStatus": market_data.get('marketStatus')
            })
        
        return jsonify({
            "status": "success",
            "order_count": len(formatted_orders),
            "orders": formatted_orders
        })
        
    except Exception as e:
        logging.error(f"Error getting working orders: {e}")
        return jsonify({
            "status": "error",
            "message": f"Error getting working orders: {str(e)}"
        }), 500

@app.route('/cancel_order/<deal_id>', methods=['POST'])
@login_required
def cancel_order(deal_id):
    """Cancel a working order"""
    try:
        # Cancel the working order through the IG API
        result = webhook_handler.trade_manager.ig_client.cancel_working_order(deal_id)
        
        if result:
            return jsonify({
                "status": "success",
                "message": f"Working order {deal_id} cancelled successfully"
            })
        else:
            return jsonify({
                "status": "error",
                "message": "Failed to cancel working order. Please check logs for details."
            }), 400
        
    except Exception as e:
        logging.error(f"Error cancelling working order: {e}")
        return jsonify({
            "status": "error",
            "message": f"Error cancelling working order: {str(e)}"
        }), 500

@app.route('/history/activity/csv', methods=['GET'])
@login_required
def download_activity_history_csv():
    """Get activity history in CSV format for download"""
    try:
        # Get query parameters
        days = request.args.get('days', default=7, type=int)
        max_results = request.args.get('max_results', default=100, type=int)
        
        # Limit the pageSize - IG API does not accept values larger than 100
        if max_results > 100:
            max_results = 100
            
        # Get IG client from webhook handler
        ig_client = webhook_handler.trade_manager.ig_client
        
        # Ensure we have a valid session
        if not ig_client._ensure_session():
            flash('Failed to connect to IG session. Please try again.', 'danger')
            return redirect(url_for('dashboard'))
        
        # Set default dates if not provided
        to_date = datetime.datetime.now()
        from_date = to_date - datetime.timedelta(days=days)
        
        # Format dates for API
        from_date_str = from_date.strftime("%Y-%m-%d")
        to_date_str = to_date.strftime("%Y-%m-%d")
        
        # Get activity history directly from IG API
        url = f"{ig_client.BASE_URL}/history/activity"
        headers = ig_client.headers.copy()
        headers['Version'] = '3'
        
        params = {
            'from': from_date_str,
            'to': to_date_str,
            'pageSize': str(max_results),  # IG API expects a string
            'detailed': 'true'  # IG API expects a string
        }
        
        # Make the API request
        response = ig_client.session.get(url, params=params, headers=headers)
        
        if response.status_code != 200:
            flash(f'IG API error: {response.status_code}', 'danger')
            return redirect(url_for('dashboard'))
        
        # Parse the JSON response
        activities_data = response.json()
        activities = activities_data.get('activities', [])
        
        if not activities:
            flash('No transactions found in the specified date range.', 'warning')
            return redirect(url_for('dashboard'))
        
        # Create a DataFrame from the activities
        activity_rows = []
        for activity in activities:
            # Extract fields from the activity object
            details = activity.get('details', {})
            row = {
                "TextEpic": details.get('epic', ''),
                "DealId": details.get('dealId', ''),
                "ActivityHistoryId": activity.get('dealId', ''),
                "Date": activity.get('date', '').split('T')[0].replace('-', '/'),
                "Time": activity.get('date', '').split('T')[1][:5] if 'T' in activity.get('date', '') else '',
                "ActivityType": activity.get('type', ''),
                "MarketName": details.get('marketName', ''),
                "Period": details.get('period', 'DFB'),
                "Result": f"{activity.get('status', '')}: {activity.get('reason', '')}",
                "Channel": details.get('channel', 'API'),
                "Currency": details.get('currency', '#.'),
                "Size": f"{'+' if details.get('direction', '') == 'BUY' else '-'}{details.get('size', '')}",
                "Level": details.get('level', ''),
                "Stop": details.get('stopLevel', ''),
                "StopType": 'N',
                "Limit": details.get('limitLevel', ''),
                "ActionStatus": activity.get('status', 'ACCEPT'),
                "Order Stop Level": '-'
            }
            activity_rows.append(row)
        
        # Create the CSV file
        df = pd.DataFrame(activity_rows)
        
        # Prepare the file name with date range
        # Fix for 'str' object has no attribute 'get'
        if isinstance(session.get('user'), str):
            account_id = session.get('user')
        else:
            account_id = session.get('user', {}).get('username', 'user')
            
        file_name = f"ActivityHistory-{account_id}-({from_date.strftime('%d-%m-%Y')})-({to_date.strftime('%d-%m-%Y')}).csv"
        
        # Create a temporary file to store the CSV
        temp_file_path = f"temp_{file_name}"
        df.to_csv(temp_file_path, index=False)
        
        # Return the CSV file
        return_data = send_file(
            temp_file_path,
            mimetype='text/csv',
            as_attachment=True,
            download_name=file_name
        )
        
        # Schedule the temp file for deletion (after response is sent)
        @return_data.call_on_close
        def delete_temp_file():
            if os.path.exists(temp_file_path):
                try:
                    os.remove(temp_file_path)
                except:
                    pass
        
        return return_data
        
    except Exception as e:
        logging.error(f"Error downloading CSV: {e}")
        flash(f'Error occurred while downloading CSV: {str(e)}', 'danger')
        return redirect(url_for('dashboard'))

@app.route('/api/history/activity', methods=['GET'])
def api_activity_history():
    """API endpoint for activity history in JSON format"""
    try:
        # Get query parameters
        days = request.args.get('days', default=7, type=int)
        max_results = request.args.get('max_results', default=100, type=int)
        
        # Limit the pageSize - IG API does not accept values larger than 100
        if max_results > 100:
            max_results = 100
            
        # Set default dates if not provided
        to_date = datetime.datetime.now()
        from_date = to_date - datetime.timedelta(days=days)
        
        # Format dates for API - IG API expects format: YYYY-MM-DD
        from_date_str = from_date.strftime("%Y-%m-%d")
        to_date_str = to_date.strftime("%Y-%m-%d")
        
        # Get IG client from webhook handler
        ig_client = webhook_handler.trade_manager.ig_client
        
        # Ensure we have a valid session
        if not ig_client._ensure_session():
            return jsonify({
                "status": "error",
                "message": "Failed to authenticate with IG API"
            }), 401
        
        # Get activity history directly from IG API
        url = f"{ig_client.BASE_URL}/history/activity"
        headers = ig_client.headers.copy()
        headers['Version'] = '3'
        
        # Prepare parameters in the correct format for IG API
        params = {
            'from': from_date_str,
            'to': to_date_str,
            'pageSize': str(max_results),  # IG API expects a string
            'detailed': 'true'  # IG API expects a string
        }
        
        # Make the API request
        logging.info(f"Getting activity history from IG API: {url} with params: {params}")
        response = ig_client.session.get(url, params=params, headers=headers)
        
        if response.status_code != 200:
            error_message = f"IG API error: {response.status_code}"
            try:
                error_json = response.json()
                if 'errorCode' in error_json:
                    error_message += f" - {error_json['errorCode']}"
            except:
                pass
                
            logging.error(f"Error from IG API: {error_message}, Response: {response.text}")
            
            return jsonify({
                "status": "error",
                "message": error_message
            }), response.status_code
        
        # Parse the JSON response
        activities_data = response.json()
        
        return jsonify({
            "status": "success",
            "from_date": from_date_str,
            "to_date": to_date_str,
            "data": activities_data
        })
        
    except Exception as e:
        logging.error(f"Error fetching activity history: {e}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@app.route('/api/update_dividend_dates', methods=['POST'])
# @login_required  # Test için geçici olarak kaldırıldı
def update_dividend_dates():
    """Update dividend dates in ticker_data.csv using Yahoo Finance data"""
    try:
        logging.info("Dividend dates update requested")
        # Run the update function
        result = update_ticker_data_dividend_dates()
        
        if result:
            logging.info("Dividend dates updated successfully")
            flash('Dividend dates updated successfully', 'success')
            return jsonify({
                "status": "success",
                "message": "Dividend dates updated successfully"
            })
        else:
            logging.error("Error updating dividend dates")
            flash('Error updating dividend dates', 'danger')
            return jsonify({
                "status": "error",
                "message": "Error updating dividend dates"
            }), 500
    
    except Exception as e:
        logging.error(f"Error updating dividend dates: {e}")
        flash(f'Error updating dividend dates: {str(e)}', 'danger')
        return jsonify({
            "status": "error",
            "message": f"Error updating dividend dates: {str(e)}"
        }), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True) 