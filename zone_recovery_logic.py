import numpy as np
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class ZoneRecoveryLogic:
    def __init__(self, stocks_data, rsi_period=14, entry_rsi_low=30, entry_rsi_high=70):
        self.stocks_data = stocks_data
        self.rsi_period = rsi_period
        self.entry_rsi_low = entry_rsi_low
        self.entry_rsi_high = entry_rsi_high
        self.rsi_values = {}

        # Initialize last_action within each stock's data structure
        for stock in self.stocks_data:
            if "last_action" not in self.stocks_data[stock]:
                self.stocks_data[stock]["last_action"] = None
            logging.debug(f"Initialized {stock} with empty last action")

    def update_price(self, stock, price):
        # Directly append the new price to the list in the stocks_data dictionary
        self.stocks_data[stock]["prices"].append(price)
        logging.debug(f"Added price {price} to {stock}")
        
        # Check if the list exceeds the RSI period and pop the oldest price if necessary
        if len(self.stocks_data[stock]["prices"]) > self.rsi_period:
            popped_price = self.stocks_data[stock]["prices"].pop(0)
            logging.debug(f"Removed oldest price {popped_price} from {stock}")

        # Calculate RSI if there are enough prices
        if len(self.stocks_data[stock]["prices"]) >= self.rsi_period:
            return self.calculate_rsi(stock)
        
        return None

    def calculate_rsi(self, stock):
        prices = np.array(self.stocks_data[stock]["prices"])
        deltas = np.diff(prices)
        gains = np.maximum(deltas, 0).sum() / self.rsi_period
        losses = -np.minimum(deltas, 0).sum() / self.rsi_period
        rs = gains / losses if losses != 0 else 0
        rsi = 100 - (100 / (1 + rs))
        self.rsi_values[stock] = rsi

        current_price = prices[-1]
        last_action = self.stocks_data[stock]["last_action"]
        if (rsi < self.entry_rsi_low and last_action != "BUY") or (rsi > self.entry_rsi_high and last_action != "SELL"):
            action = "BUY" if rsi < self.entry_rsi_low else "SELL"
            self.stocks_data[stock]["last_action"] = action
            logging.info(f"{stock}: RSI {rsi} triggered a {action} action at price {current_price}")
            return action, current_price
        
        logging.info(f"{stock}: RSI {rsi} did not trigger any action. Last action was {last_action}")
        return None
