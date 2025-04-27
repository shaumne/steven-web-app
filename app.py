"""
Main application for the Trading Bot webhook server
"""
import os
import logging
import json
from flask import Flask, request, jsonify
from trading_bot.webhook_handler import WebhookHandler
from trading_bot.config import load_ticker_data

# Initialize Flask app
app = Flask(__name__)

# Initialize webhook handler
webhook_handler = WebhookHandler()

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

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True) 