import logging
import pandas as pd
from trading_bot.trade_calculator import TradeCalculator

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Load ticker data
df = pd.read_csv('ticker_data.csv')

# Initialize calculator
calc = TradeCalculator(df)

# Test calculation for LSE_DLY:SRP with UP direction
ticker = 'LSE_DLY:SRP'
direction = 'UP'
opening_price = 189.8
atr_values = [0.6, 1.819, 2.378, 2.839, 3.204, 3.478, 3.68, 3.83, 3.94, 4.023]

# Calculate trade parameters
result = calc.calculate_trade_parameters(ticker, direction, opening_price, atr_values)

# Print results
print("\n=== CALCULATION RESULTS ===")
print(f"Ticker: {ticker}")
print(f"Direction: {direction}")
print(f"Opening Price: {opening_price}")
print(f"Entry Price: {result['price_level']}")
print(f"Stop Level: {result['stop_level']}")
print(f"Limit Level: {result['limit_level']}")
print(f"Stop Distance: {result['stop_distance']}")
print(f"Limit Distance: {result['limit_distance']}")
print(f"Position Size: {result['position_size']}")
print("\n=== EXPECTED VALUES ===")
print(f"Expected Entry Price: 191.70 (189.8*1.01)")
print(f"Expected Stop Level: 195.16 ((2.839*1.89)+189.8)")
print(f"Expected Limit Level: 183.54 (189.8-(3.478*1.8))")
print("\n=== FULL RESULT OBJECT ===")
for key, value in result.items():
    print(f"{key}: {value}") 