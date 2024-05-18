import os
import requests
import logging
from dotenv import load_dotenv
import numpy as np

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class GetMarketData:
    def __init__(self):
        load_dotenv()  # Load environment variables from .env file
        self.api_key = os.getenv('TRADING_KEY')  # Retrieve API key from environment variable
        self.base_url = "https://www.alphavantage.co/query"  # Base URL for API requests
        self.short_term_window = 20
        self.long_term_window = 50

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

    def fetch_intraday_data(self, symbol, interval="1min", mode="realtime"):
        """Fetch the latest intraday data."""
        params = self._get_params("TIME_SERIES_INTRADAY", symbol, interval, "compact", mode)
        data = self._make_api_request(params)
        return {time: float(info['4. close']) for time, info in data.get("Time Series (1min)", {}).items()}

    def fetch_initial_data(self, symbol, interval="1min", period=30, mode="realtime", series="TIME_SERIES_INTRADAY"):
        """Fetch the initial set of data for RSI calculation including timestamps and volumes."""
        params = self._get_params(series, symbol, interval, "full", mode)
        data = self._make_api_request(params)

        # Determine the correct key for time series data based on the series type
        if series == "TIME_SERIES_INTRADAY":
            time_series_key = "Time Series (1min)"
        elif series == "TIME_SERIES_DAILY":
            time_series_key = "Time Series (Daily)"
        else:
            logging.error("Unsupported time series type")
            return [], []

        time_series = data.get(time_series_key, {})
        sorted_times = sorted(time_series.keys())[-period:]  # Get the last `period` entries

        # Return both prices and their respective timestamps and volumes as lists of tuples
        return [(float(time_series[time]['4. close']), time) for time in sorted_times], \
               [int(time_series[time]['5. volume']) for time in sorted_times]

    def fetch_latest_price(self, symbol, interval="1min", mode="realtime"):
        """Fetch the most recent price for the specified stock symbol along with its timestamp."""
        params = self._get_params("TIME_SERIES_INTRADAY", symbol, interval, "compact", mode)
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

    def filter_stocks_by_price(self, price_limit=10, max_stocks_to_trade=10):
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
                    if len(low_price_stocks) >= max_stocks_to_trade:
                        break
        return low_price_stocks

    def get_potential_candidates(self, price_limit=10):
        """Fetch potential stock candidates by analyzing trends."""
        candidates = self.filter_stocks_by_price(price_limit)
        potential_candidates = []

        for candidate in candidates:
            historical_data, volumes = self.fetch_initial_data(candidate, "1day", 365, "delayed", "TIME_SERIES_DAILY")
            entry_signal = self.analyze_trend(historical_data, volumes, support_level=0.8, resistance_level=1.2)  # Adjust support and resistance as needed
            if entry_signal in ["Buy", "Sell"]:
                potential_candidates.append((candidate, entry_signal))
                logging.info(f"Added {candidate} to potential candidates based on trend analysis with signal {entry_signal}.")

        return potential_candidates

    def calculate_rsi(self, prices, period=14):
        """Calculate the Relative Strength Index (RSI)."""
        deltas = np.diff(prices)
        seed = deltas[:period+1]
        up = seed[seed >= 0].sum() / period
        down = -seed[seed < 0].sum() / period
        rs = up / down
        rsi = np.zeros_like(prices)
        rsi[:period] = 100. - 100. / (1. + rs)

        for i in range(period, len(prices)):
            delta = deltas[i - 1]
            if delta > 0:
                upval = delta
                downval = 0.
            else:
                upval = 0.
                downval = -delta

            up = (up * (period - 1) + upval) / period
            down = (down * (period - 1) + downval) / period

            rs = up / down
            rsi[i] = 100. - 100. / (1. + rs)

        return rsi

    def analyze_trend(self, historical_data, volumes, support_level, resistance_level):
        """Analyze trend based on moving averages and other indicators."""
        # Extract prices from the historical data tuples
        prices = np.array([price for price, date in historical_data])

        if len(prices) >= self.long_term_window:
            sma_short = np.mean(prices[-self.short_term_window:])
            sma_long = np.mean(prices[-self.long_term_window:])
            rsi = self.calculate_rsi(prices)[-1]
            current_price = prices[-1]
            current_volume = volumes[-1]
            average_volume = np.mean(volumes)

            trend = "neutral"
            entry_signal = "Hold"

            if sma_short > sma_long:
                trend = "upward"
                logging.info(f"Upward trend detected with SMA {sma_short} and LMA {sma_long}")
            elif sma_short < sma_long:
                trend = "downward"
                logging.info(f"Downward trend detected with SMA {sma_short} and LMA {sma_long}")

            logging.info(f"Current price: {current_price}")
            if trend == "upward" and current_volume > average_volume and rsi < 30 and current_price > resistance_level:
                entry_signal = "Buy"
            elif trend == "downward" and current_volume > average_volume and rsi > 70 and current_price < support_level:
                entry_signal = "Sell"

            logging.info(f"Trend: {trend}, RSI: {rsi}, Volume: {current_volume}, Average Volume: {average_volume}, Support: {support_level}, Resistance: {resistance_level}, Entry Signal: {entry_signal}")

            return entry_signal

        return "Hold"

# Example usage
if __name__ == "__main__":
    market_data = GetMarketData()
    candidates = market_data.get_potential_candidates()
    logging.info(f"Potential trading candidates: {candidates}")
