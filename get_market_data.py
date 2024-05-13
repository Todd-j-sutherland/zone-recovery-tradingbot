import os
import requests
import logging
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class GetMarketData:
    def __init__(self):
        load_dotenv()  # Load environment variables from .env file
        self.api_key = os.getenv('TRADING_KEY')  # Retrieve API key from environment variable
        self.base_url = "https://www.alphavantage.co/query"  # Base URL for API requests

    def _make_api_request(self, symbol, interval, outputsize):
        """ Private method to handle API requests. """
        params = {
            "function": "TIME_SERIES_INTRADAY",
            "symbol": symbol,
            "interval": interval,
            "apikey": self.api_key,
            "outputsize": outputsize
        }
        try:
            response = requests.get(self.base_url, params=params)
            response.raise_for_status()  # Will raise an HTTPError for bad requests (4XX, 5XX)
            return response.json()
        except requests.RequestException as e:
            logging.error(f"API request error: {e}")
            return {}

    def fetch_intraday_data(self, symbol, interval="1min"):
        """ Fetch the latest intraday data. """
        data = self._make_api_request(symbol, interval, "compact")
        return {time: float(info['4. close']) for time, info in data.get("Time Series (1min)", {}).items()}

    def fetch_initial_data(self, symbol, interval="1min", period=30):
        """ Fetch the initial set of data for RSI calculation. """
        data = self._make_api_request(symbol, interval, "full")
        time_series = data.get("Time Series (1min)", {})
        sorted_times = sorted(time_series.keys())[-period:]  # Ensure only the last `period` minutes are returned
        return [float(time_series[time]['4. close']) for time in sorted_times]

    def fetch_latest_price(self, symbol, interval="1min"):
        """ Fetch the most recent price for the specified stock symbol. """
        data = self._make_api_request(symbol, interval, "compact")
        time_series = data.get("Time Series (1min)", {})
        latest_time = max(time_series.keys(), default=None)
        if latest_time:
            latest_price = float(time_series[latest_time]['4. close'])
            logging.info(f"Latest price for {symbol}: {latest_price}")
            return latest_price
        logging.warning(f"No latest price data available for {symbol}")
        return None

# Example usage
if __name__ == "__main__":
    market_data = GetMarketData()
    latest_price = market_data.fetch_latest_price("TSLY", "1min")
    initial_data = market_data.fetch_initial_data("TSLY", "1min", 30)
    logging.info(f"Latest price: {latest_price}")
    logging.info(f"Initial data: {initial_data}")
