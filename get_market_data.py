import os
import requests
import logging
from dotenv import load_dotenv
import numpy as np  # Make sure to import numpy for trend analysis

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class GetMarketData:
    def __init__(self):
        load_dotenv()  # Load environment variables from .env file
        self.api_key = os.getenv('TRADING_KEY')  # Retrieve API key from environment variable
        self.base_url = "https://www.alphavantage.co/query"  # Base URL for API requests

    def _make_api_request(self, params):
        """Private method to handle API requests."""
        params['apikey'] = self.api_key  # Add the API key to the parameters
        try:
            response = requests.get(self.base_url, params=params)
            response.raise_for_status()  # Raises HTTPError for bad requests
            return response.json()
        except requests.RequestException as e:
            logging.error(f"API request error: {e}")
            return {}

    def _get_params(self, function, symbol=None, interval=None, outputsize=None, entitlement=None):
        """Generate parameters dictionary for API requests."""
        params = {"function": function}
        if symbol:
            params["symbol"] = symbol
        if interval:
            params["interval"] = interval
        if outputsize:
            params["outputsize"] = outputsize
        if entitlement:
            params["entitlement"] = entitlement
        return params

    def fetch_intraday_data(self, symbol, interval="1min"):
        """Fetch the latest intraday data."""
        params = self._get_params("TIME_SERIES_INTRADAY", symbol, interval, "compact", "realtime")
        data = self._make_api_request(params)
        return {time: float(info['4. close']) for time, info in data.get("Time Series (1min)", {}).items()}

    def fetch_initial_data(self, symbol, interval="1min", period=30):
        """Fetch the initial set of data for RSI calculation including timestamps."""
        params = self._get_params("TIME_SERIES_INTRADAY", symbol, interval, "full", "realtime")
        data = self._make_api_request(params)
        time_series = data.get("Time Series (1min)", {})
        sorted_times = sorted(time_series.keys())[-period:]  # Get the last `period` minutes
        
        # Return both prices and their respective timestamps as a list of tuples
        return [(float(time_series[time]['4. close']), time) for time in sorted_times]

    def fetch_latest_price(self, symbol, interval="1min"):
        """Fetch the most recent price for the specified stock symbol along with its timestamp."""
        params = self._get_params("TIME_SERIES_INTRADAY", symbol, interval, "compact", "realtime")
        data = self._make_api_request(params)
        time_series = data.get("Time Series (1min)", {})
        latest_time = max(time_series.keys(), default=None)
        if latest_time:
            latest_price = float(time_series[latest_time]['4. close'])
            logging.info(f"Latest price for {symbol}: {latest_price} at {latest_time}")
            return latest_price, latest_time
        logging.warning(f"No latest price data available for {symbol}")
        return None, None

    def fetch_top_gainers_losers_most_traded(self):
        """Fetch the top gainers, losers, and most actively traded stocks in the US market."""
        params = {
            "function": "TOP_GAINERS_LOSERS",
            "interval": "5min"  # Ensure this matches available API parameters if needed
        }
        result = self._make_api_request(params)
        return result

    def filter_stocks_by_price(self, price_limit=10):
        """Filter stocks from all categories (gainers, losers, most traded) with price below a certain limit."""
        data = self.fetch_top_gainers_losers_most_traded()
        low_price_stocks = []

        categories = ['top_gainers', 'top_losers', 'most_actively_traded']
        for category in categories:
            stocks = data.get(category, [])
            for stock in stocks:
                if float(stock['price']) <= price_limit:
                    low_price_stocks.append(stock['ticker'])
                    logging.info(f"Added {stock['ticker']} from {category} with price {stock['price']}")
        print(low_price_stocks)
        return low_price_stocks

    def get_potential_candidates(self, price_limit=10):
        """Fetch potential stock candidates by analyzing trends."""
        candidates = self.filter_stocks_by_price(price_limit)
        potential_candidates = []

        for candidate in candidates:
            historical_data = self.fetch_initial_data(candidate, "1day", 365)
            if self.analyze_trend(historical_data):
                potential_candidates.append(candidate)
                logging.info(f"Added {candidate} to potential candidates based on trend analysis.")

        return potential_candidates

    def analyze_trend(self, historical_data):
        """Analyze trend based on moving averages."""
        prices = np.array([price for price, _ in historical_data])
        
        short_term_window = 20
        long_term_window = 50
        
        if len(prices) >= long_term_window:
            sma_short = np.mean(prices[-short_term_window:])
            sma_long = np.mean(prices[-long_term_window:])
            
            if sma_short > sma_long:
                logging.info(f"Upward trend detected with SMA {sma_short} and LMA {sma_long}")
                return True
            elif sma_short < sma_long:
                logging.info(f"Downward trend detected with SMA {sma_short} and LMA {sma_long}")
                return True
        
        return False

# Example usage
if __name__ == "__main__":
    market_data = GetMarketData()
    top_stocks = market_data.filter_stocks_by_price(10)
    logging.info(f"Top stocks under $10: {top_stocks}")
    candidates = market_data.get_potential_candidates()
    logging.info(f"Top stocks under $10: {candidates}")
