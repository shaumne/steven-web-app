"""
Pipedream webhook handler for the Trading Bot
"""
import os
import json
import logging
from datetime import datetime
import pandas as pd
from trading_bot.webhook_handler import WebhookHandler

def handler(event, context):
    """
    Pipedream handler function
    
    Args:
        event: The event data from Pipedream
        context: The context from Pipedream
        
    Returns:
        dict: The result of processing the webhook
    """
    # Set up logging for Pipedream
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Get the request body from the event
    if 'body' in event:
        try:
            # Try to parse as JSON
            if isinstance(event['body'], str):
                body = json.loads(event['body'])
            else:
                body = event['body']
        except json.JSONDecodeError:
            # If not JSON, use as string
            body = event['body']
    else:
        # If no body, use the event itself
        body = event
    
    # Initialize the webhook handler
    webhook_handler = WebhookHandler()
    
    # Process the webhook
    result = webhook_handler.process_webhook(body)
    
    # Return the result
    return {
        "statusCode": 200 if result.get('status') == 'success' else 400,
        "body": json.dumps(result),
        "headers": {
            "Content-Type": "application/json"
        }
    } 