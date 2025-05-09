import yfinance as yf
import pandas as pd
import csv
from datetime import datetime, date
import os
import logging

# Cache konumunu projenin bulunduğu dizine ayarla
cache_dir = os.path.join(os.path.dirname(__file__), '.cache', 'yfinance')
os.makedirs(cache_dir, exist_ok=True)
yf.set_tz_cache_location(cache_dir)

# Mapping dictionary for exchange prefixes
EXCHANGE_TO_YAHOO_MAPPING = {
    "ASX_DLY": ".AX",       # Australian Securities Exchange
    "BATS": "",             # BATS US (no suffix needed)
    "LSE_DLY": ".L",        # London Stock Exchange
    "TSX_DLY": ".TO",       # Toronto Stock Exchange
    "HKEX_DLY": ".HK",      # Hong Kong Stock Exchange
    "TSE_DLY": ".T",        # Tokyo Stock Exchange
    "EURONEXT_DLY": ".AS",  # Euronext Amsterdam
    "VIE_DLY": ".VI",       # Vienna Stock Exchange
    "XETR_DLY": ".DE"       # Deutsche Börse Xetra
}

def convert_to_yahoo_symbol(ig_symbol):
    """
    Convert IG Markets symbol format to Yahoo Finance format
    
    Args:
        ig_symbol (str): Symbol in IG Markets format (e.g., ASX_DLY:IFL)
        
    Returns:
        str: Symbol in Yahoo Finance format (e.g., IFL.AX)
    """
    if not ig_symbol or ":" not in ig_symbol:
        return None
        
    exchange, ticker = ig_symbol.split(":")
    
    # Special case for certain tickers
    if ticker == "BP.":
        ticker = "BP"
    
    # Get the suffix for the exchange
    suffix = EXCHANGE_TO_YAHOO_MAPPING.get(exchange, "")
    
    if not suffix and exchange != "BATS":
        print(f"Warning: Unknown exchange prefix: {exchange}")
        return None
    
    # Format the Yahoo Finance ticker
    yahoo_symbol = f"{ticker}{suffix}"
    
    return yahoo_symbol

def get_next_dividend_date(ticker_symbol):
    """
    Returns the future dividend dates for a stock
    
    Args:
        ticker_symbol (str): Stock symbol in Yahoo Finance format
        
    Returns:
        dict: Dictionary containing future dividend dates and information
    """
    try:
        # Get stock information from Yahoo Finance
        stock = yf.Ticker(ticker_symbol)
        
        # Get all stock information
        info = stock.info
        
        # Extract dividend date information
        dividend_info = {}
        
        # Future ex-dividend date
        if 'exDividendDate' in info and info['exDividendDate'] is not None:
            ex_date_timestamp = info['exDividendDate']
            # Convert Unix timestamp to datetime
            ex_date = datetime.fromtimestamp(ex_date_timestamp).date()
            
            # If ex-dividend date is today or later, it's a future dividend
            if ex_date >= date.today():
                dividend_info['next_ex_dividend_date'] = ex_date.strftime('%Y-%m-%d')
            else:
                dividend_info['next_ex_dividend_date'] = None
        else:
            dividend_info['next_ex_dividend_date'] = None
            
        # Dividend payment date
        if 'dividendDate' in info and info['dividendDate'] is not None:
            payment_date_timestamp = info['dividendDate']
            # Convert Unix timestamp to datetime
            payment_date = datetime.fromtimestamp(payment_date_timestamp).date()
            
            # If payment date is today or later, it's a future dividend
            if payment_date >= date.today():
                dividend_info['next_payment_date'] = payment_date.strftime('%Y-%m-%d')
            else:
                dividend_info['next_payment_date'] = None
        else:
            dividend_info['next_payment_date'] = None
            
        # Dividend amount
        if 'dividendRate' in info and info['dividendRate'] is not None:
            dividend_info['dividend_amount'] = info['dividendRate']
        else:
            dividend_info['dividend_amount'] = None
            
        # Dividend yield (%)
        if 'dividendYield' in info and info['dividendYield'] is not None:
            dividend_info['dividend_yield'] = round(info['dividendYield'] * 100, 2)
        else:
            dividend_info['dividend_yield'] = None
            
        # If there's no future dividend date, show the last ex-dividend date
        if dividend_info['next_ex_dividend_date'] is None:
            dividends = stock.dividends
            if not dividends.empty:
                last_ex_date = dividends.index[-1].date()
                dividend_info['last_ex_dividend_date'] = last_ex_date.strftime('%Y-%m-%d')
            else:
                dividend_info['last_ex_dividend_date'] = None
        
        # Add the original symbol for reference
        dividend_info['yahoo_symbol'] = ticker_symbol
            
        return dividend_info
        
    except Exception as e:
        print(f"Error occurred for symbol {ticker_symbol}: {e}")
        return {"error": str(e), "yahoo_symbol": ticker_symbol}

def format_dividend_info(ig_symbol, yahoo_symbol, dividend_info):
    """
    Formats dividend information into a readable text
    
    Args:
        ig_symbol (str): Stock symbol in IG format
        yahoo_symbol (str): Stock symbol in Yahoo format
        dividend_info (dict): Dictionary containing dividend information
        
    Returns:
        str: Readable dividend information
    """
    result = f"Dividend Information: {ig_symbol} (Yahoo: {yahoo_symbol})\n"
    result += "-" * 60 + "\n"
    
    if 'error' in dividend_info:
        return f"Error for {ig_symbol}: {dividend_info['error']}"
    
    # Next ex-dividend date
    if dividend_info.get('next_ex_dividend_date'):
        result += f"Next Ex-Dividend Date: {dividend_info['next_ex_dividend_date']}\n"
    else:
        result += "Next Ex-Dividend Date: No information available\n"
        
    # Next payment date
    if dividend_info.get('next_payment_date'):
        result += f"Next Payment Date: {dividend_info['next_payment_date']}\n"
    else:
        result += "Next Payment Date: No information available\n"
        
    # Dividend amount
    if dividend_info.get('dividend_amount'):
        result += f"Dividend Amount: {dividend_info['dividend_amount']}\n"
    else:
        result += "Dividend Amount: No information available\n"
        
    # Dividend yield
    if dividend_info.get('dividend_yield'):
        result += f"Dividend Yield: {dividend_info['dividend_yield']}%\n"
    else:
        result += "Dividend Yield: No information available\n"
        
    # Last ex-dividend date
    if 'last_ex_dividend_date' in dividend_info and dividend_info['last_ex_dividend_date']:
        result += f"Last Ex-Dividend Date: {dividend_info['last_ex_dividend_date']}\n"
    
    return result

def load_ticker_data(csv_file_path="ticker_data.csv"):
    """
    Load ticker data from CSV file
    
    Args:
        csv_file_path (str): Path to the CSV file
        
    Returns:
        pandas.DataFrame: DataFrame containing ticker data
    """
    try:
        df = pd.read_csv(csv_file_path)
        return df
    except Exception as e:
        print(f"Error loading ticker data: {e}")
        return None

def update_csv_with_dividend_dates(csv_file_path="ticker_data.csv", output_file=None):
    """
    Update CSV with next dividend dates from Yahoo Finance
    
    Args:
        csv_file_path (str): Path to the CSV file
        output_file (str): Path to the output file. If None, updates original file.
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Load the CSV file
        df = load_ticker_data(csv_file_path)
        if df is None:
            return False
        
        # Create a new column for the next dividend date if it doesn't exist
        if 'Yahoo Next Dividend Date' not in df.columns:
            df['Yahoo Next Dividend Date'] = None
        
        # Process each row in the DataFrame
        results = []
        
        for index, row in df.iterrows():
            ig_symbol = row['Symbol']
            print(f"Processing {ig_symbol}...")
            
            # Convert to Yahoo Finance format
            yahoo_symbol = convert_to_yahoo_symbol(ig_symbol)
            if not yahoo_symbol:
                print(f"  Skipping {ig_symbol}: Could not convert to Yahoo format")
                results.append({
                    'IG Symbol': ig_symbol,
                    'Yahoo Symbol': 'N/A',
                    'Next Dividend Date': 'N/A',
                    'Status': 'Conversion error'
                })
                continue
            
            # Get dividend information
            try:
                dividend_info = get_next_dividend_date(yahoo_symbol)
                
                # Extract the next dividend date
                next_date = dividend_info.get('next_ex_dividend_date')
                
                # Update the DataFrame
                df.at[index, 'Yahoo Next Dividend Date'] = next_date if next_date else "No future dividend"
                
                # Add to results
                results.append({
                    'IG Symbol': ig_symbol,
                    'Yahoo Symbol': yahoo_symbol,
                    'Next Dividend Date': next_date if next_date else "None",
                    'Status': 'Success' if not 'error' in dividend_info else f"Error: {dividend_info['error']}"
                })
                
                # Print dividend information
                if not 'error' in dividend_info:
                    print(format_dividend_info(ig_symbol, yahoo_symbol, dividend_info))
                else:
                    print(f"  Error for {ig_symbol}: {dividend_info.get('error')}")
                
            except Exception as e:
                print(f"  Error processing {ig_symbol}: {e}")
                results.append({
                    'IG Symbol': ig_symbol,
                    'Yahoo Symbol': yahoo_symbol,
                    'Next Dividend Date': 'N/A',
                    'Status': f'Processing error: {str(e)}'
                })
        
        # Save the updated DataFrame
        if output_file:
            df.to_csv(output_file, index=False)
            print(f"Updated data saved to {output_file}")
        else:
            # Backup the original file
            backup_file = f"{csv_file_path}.bak"
            if os.path.exists(csv_file_path):
                df_original = pd.read_csv(csv_file_path)
                df_original.to_csv(backup_file, index=False)
                print(f"Original data backed up to {backup_file}")
            
            # Save the updated data to the original file
            df.to_csv(csv_file_path, index=False)
            print(f"Updated data saved to {csv_file_path}")
        
        # Create a results DataFrame
        results_df = pd.DataFrame(results)
        results_file = "dividend_check_results.csv"
        results_df.to_csv(results_file, index=False)
        print(f"Results saved to {results_file}")
        
        return True
        
    except Exception as e:
        print(f"Error updating CSV: {e}")
        return False

def check_specific_symbols(symbols):
    """
    Check dividend dates for specific symbols
    
    Args:
        symbols (list): List of symbols in IG format
        
    Returns:
        list: List of dictionaries with dividend information
    """
    results = []
    
    for ig_symbol in symbols:
        print(f"\nChecking {ig_symbol}...")
        
        # Convert to Yahoo Finance format
        yahoo_symbol = convert_to_yahoo_symbol(ig_symbol)
        if not yahoo_symbol:
            print(f"  Could not convert {ig_symbol} to Yahoo format")
            continue
        
        # Get dividend information
        dividend_info = get_next_dividend_date(yahoo_symbol)
        
        # Print dividend information
        print(format_dividend_info(ig_symbol, yahoo_symbol, dividend_info))
        
        # Add to results
        results.append({
            'ig_symbol': ig_symbol,
            'yahoo_symbol': yahoo_symbol,
            'dividend_info': dividend_info
        })
    
    return results

def export_dividend_dates_to_csv(csv_file_path="ticker_data.csv", output_file="dividend_dates.csv"):
    """
    Export next dividend dates from CSV file to a separate CSV file
    
    Args:
        csv_file_path (str): Path to the input CSV file
        output_file (str): Path to the output CSV file
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Load the CSV file
        df = load_ticker_data(csv_file_path)
        if df is None:
            return False
        
        # Get dividend information for each ticker
        results = []
        
        for index, row in df.iterrows():
            ig_symbol = row['Symbol']
            print(f"Processing {ig_symbol}...")
            
            # Convert to Yahoo Finance format
            yahoo_symbol = convert_to_yahoo_symbol(ig_symbol)
            if not yahoo_symbol:
                print(f"  Skipping {ig_symbol}: Could not convert to Yahoo format")
                continue
            
            # Get dividend information
            try:
                dividend_info = get_next_dividend_date(yahoo_symbol)
                
                # Extract the next dividend date
                next_date = dividend_info.get('next_ex_dividend_date')
                
                # Add to results if there is a future dividend date
                if next_date:
                    results.append({
                        'Ticker': ig_symbol,
                        'Yahoo Symbol': yahoo_symbol,
                        'Next Ex-Dividend Date': next_date
                    })
                    print(f"  Found next dividend date for {ig_symbol}: {next_date}")
                else:
                    print(f"  No future dividend date for {ig_symbol}")
                
            except Exception as e:
                print(f"  Error processing {ig_symbol}: {e}")
        
        # Create a results DataFrame
        if results:
            results_df = pd.DataFrame(results)
            results_df.to_csv(output_file, index=False)
            print(f"\nDividend dates exported to {output_file}")
            print(f"Found {len(results)} stocks with upcoming dividend dates")
            return True
        else:
            print("\nNo stocks with upcoming dividend dates found")
            return False
        
    except Exception as e:
        print(f"Error exporting dividend dates: {e}")
        return False

def update_ticker_data_dividend_dates(csv_file_path="ticker_data.csv"):
    """
    Update the 'Next dividend date' column in ticker_data.csv with data from Yahoo Finance
    
    Args:
        csv_file_path (str): Path to the CSV file
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Load the CSV file
        df = load_ticker_data(csv_file_path)
        if df is None:
            return False
        
        # Make sure the column exists
        if 'Next dividend date' not in df.columns:
            df['Next dividend date'] = None
        
        # Ensure the column is string type
        df['Next dividend date'] = df['Next dividend date'].astype('object')
        
        # Process each row in the DataFrame
        update_count = 0
        for index, row in df.iterrows():
            ig_symbol = row['Symbol']
            print(f"Processing {ig_symbol}...")
            
            # Convert to Yahoo Finance format
            yahoo_symbol = convert_to_yahoo_symbol(ig_symbol)
            if not yahoo_symbol:
                print(f"  Skipping {ig_symbol}: Could not convert to Yahoo format")
                continue
            
            # Get dividend information
            try:
                dividend_info = get_next_dividend_date(yahoo_symbol)
                
                # Extract the next dividend date
                next_date = dividend_info.get('next_ex_dividend_date')
                
                # Update the DataFrame if we have a date
                if next_date:
                    # Convert YYYY-MM-DD to DD/MM/YYYY format
                    date_parts = next_date.split('-')
                    formatted_date = f"{date_parts[2]}/{date_parts[1]}/{date_parts[0]}"
                    
                    df.at[index, 'Next dividend date'] = formatted_date
                    update_count += 1
                    print(f"  Updated {ig_symbol} with next dividend date: {formatted_date}")
                else:
                    print(f"  No future dividend date for {ig_symbol}")
                
            except Exception as e:
                print(f"  Error processing {ig_symbol}: {e}")
        
        # Save the updated DataFrame
        backup_file = f"{csv_file_path}.bak"
        df_original = pd.read_csv(csv_file_path)
        df_original.to_csv(backup_file, index=False)
        print(f"Original data backed up to {backup_file}")
        
        df.to_csv(csv_file_path, index=False)
        print(f"\nUpdated ticker_data.csv with {update_count} dividend dates")
        return True
        
    except Exception as e:
        print(f"Error updating CSV: {e}")
        return False

# Test the function with a specific symbol
if __name__ == "__main__":
    # Uncomment the appropriate section based on what you want to do
    
    # Option 1: Check a single symbol
    # symbols_to_check = ["BATS:IBM"]
    # results = check_specific_symbols(symbols_to_check)
    
    # Option 2: Update the entire CSV file
    # update_csv_with_dividend_dates("ticker_data.csv")
    
    # Option 3: Export dividend dates to separate CSV file
    # export_dividend_dates_to_csv("ticker_data.csv", "dividend_dates.csv")
    
    # Option 4: Update the 'Next dividend date' column in ticker_data.csv
    update_ticker_data_dividend_dates("ticker_data.csv")
