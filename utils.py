import pandas as pd
import ta

def calculate_rsi(prices, rsi_period=14):
    # Create a DataFrame from the prices
    df = pd.DataFrame(prices, columns=['price'])

    # Calculate the RSI using the ta library
    rsi_series = ta.momentum.RSIIndicator(df['price'], window=rsi_period).rsi()

    # Return the last RSI value
    return rsi_series.iloc[-1]
