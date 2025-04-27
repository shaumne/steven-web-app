# Trading Bot

A Python-based trading bot that processes alerts from TradingView and executes trades on IG Markets based on predefined parameters.

## Overview

This bot listens for webhook alerts from TradingView, processes them, and executes trades on IG Markets. It includes various validation checks and uses a CSV file for ticker-specific configuration.

## Features

- Processes webhook alerts from TradingView
- Validates alerts based on various criteria
- Calculates trade parameters using ATR values
- Executes trades on IG Markets via their API
- Automatically retrieves EPIC codes from IG Markets API
- Tracks and monitors position status via API
- Tracks daily trades to avoid duplicates
- Handles errors gracefully
- Logs all operations

## Alert Format

The bot expects TradingView alerts in the following format:

```
TICKER DIRECTION OPENING_PRICE ATR1 ATR2 ATR3 ATR4 ATR5 ATR6 ATR7 ATR8 ATR9 ATR10
```

Example:
```
BATS:PML UP 7.51 50.53 48.22 45.44 42.65 41.23 40.89 40.55 40.22 40.09 40.01
```

- `TICKER`: The symbol (e.g., BATS:PML)
- `DIRECTION`: UP or DOWN
- `OPENING_PRICE`: Today's opening price
- `ATR1` to `ATR10`: ATR values for periods 1 to 10

## CSV Configuration

The bot uses a CSV file to store ticker-specific configuration. The CSV should have the following columns:

- `Symbol`: Ticker symbol as it appears in TradingView alerts
- `IG EPIC`: IG Markets EPIC code for the instrument (optional, will be fetched from API if not provided)
- `ATR Stop Loss Period`: Which ATR period to use for stop loss
- `ATR Stop Loss Multiple`: Multiplier for stop loss
- `ATR Profit Target Period`: Which ATR period to use for take profit
- `ATR Profit Multiple`: Multiplier for take profit
- `Postion Size Max GBP`: Maximum position size in GBP
- `Opening Price Multiple`: Multiplier for entry price
- `Next dividend date`: Date of the next dividend (will skip trades on this date)

## EPIC Code Retrieval

The bot has two methods for getting EPIC codes for instruments:

1. From the CSV file: If the `IG EPIC` column is populated, it will use that value.
2. From the IG Markets API: If the `IG EPIC` is not available in the CSV or marked as `?`, the bot will automatically search for the instrument on IG Markets and retrieve the EPIC code.

The bot maintains a cache of EPIC codes to avoid repeated API calls for the same symbol.

## Position Status Tracking

The bot provides several endpoints to track and monitor your positions:

1. `/positions`: Get all current open positions
2. `/position/status?reference=DEAL_REFERENCE`: Check the status of a specific position by its deal reference
3. `/position/status?ticker=TICKER`: Check the status of a position for a specific ticker
4. `/position/today`: Get all trades made today

The bot retrieves position status information directly from the IG Markets API, ensuring you always have the most up-to-date information about your trades.

## Setup

1. Clone this repository
2. Install dependencies: `pip install -r requirements.txt`
3. Copy `.env-example` to `.env` and update with your credentials
4. Place your CSV file in the directory (default name: `ticker_data.csv`)
5. Run the bot: `python app.py`

## Deployment

### Local/Server Deployment

For a traditional server deployment:

1. Set up your environment variables
2. Run with Gunicorn: `gunicorn app:app`

### Pipedream Deployment

For Pipedream:

1. Upload the code to Pipedream
2. Configure environment variables in Pipedream
3. Set the handler function to `pipedream_webhook.handler`

## Environment Variables

- `IG_USERNAME`: IG Markets username
- `IG_PASSWORD`: IG Markets password
- `IG_API_KEY`: IG Markets API key
- `IG_ACCOUNT_TYPE`: Account type (DEMO or LIVE)
- `CSV_FILE_PATH`: Path to the CSV configuration file
- `FLASK_ENV`: Flask environment (development or production)
- `PORT`: Port for the Flask server

## Testing

You can test the bot by:

1. Visiting the `/test` endpoint to check if the CSV file is loaded correctly
2. Sending a test alert to the `/webhook` endpoint
3. Checking position status via the `/positions` or `/position/status` endpoints 