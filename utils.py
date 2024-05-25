import pandas as pd
import ta

def calculate_rsi(prices, rsi_period=14):
    # Create a DataFrame from the prices
    df = pd.DataFrame(prices, columns=['price'])

    # Calculate the RSI using the ta library
    rsi_series = ta.momentum.RSIIndicator(df['price'], window=rsi_period).rsi()

    # Return the last RSI value
    return rsi_series.iloc[-1]

def calculate_moving_average(prices, period):
    # Convert the prices to a DataFrame
    prices_df = pd.DataFrame(prices, columns=['close'])
    
    # Initialize the SMA (Simple Moving Average) with the given period
    sma = ta.trend.SMAIndicator(prices_df['close'], window=period)
    
    # Get the SMA values
    moving_average = sma.sma_indicator()
    
    # Return the last value of the moving average
    return moving_average.iloc[-1] if not moving_average.empty else None