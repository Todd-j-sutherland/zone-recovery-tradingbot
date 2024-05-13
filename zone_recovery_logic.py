import numpy as np
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class ZoneRecoveryLogic:
    def __init__(self, stocks_data, rsi_period=14, entry_rsi_low=30, entry_rsi_high=70, profit_target=0.05):
        self.stocks_data = stocks_data
        self.rsi_period = rsi_period
        self.entry_rsi_low = entry_rsi_low
        self.entry_rsi_high = entry_rsi_high
        self.profit_target = profit_target  # 5% profit target
        self.rsi_values = {}

        # Initialize data structures
        for stock in self.stocks_data:
            self.stocks_data[stock].setdefault("last_action", None)
            self.stocks_data[stock].setdefault("entry_price", None)
            logging.debug(f"Initialized {stock} with empty last action and no entry price.")

    def update_price(self, stock, price):
        # Directly append the new price to the list in the stocks_data dictionary
        self.stocks_data[stock]["prices"].append(price)
        
        # Check if the list exceeds the RSI period and pop the oldest price if necessary
        if len(self.stocks_data[stock]["prices"]) > self.rsi_period:
            self.stocks_data[stock]["prices"].pop(0)

        # Calculate RSI if there are enough prices
        if len(self.stocks_data[stock]["prices"]) >= self.rsi_period:
            return self.calculate_rsi_and_check_profit(stock, price)
        
        return None

    def calculate_rsi_and_check_profit(self, stock, current_price):
        prices = np.array(self.stocks_data[stock]["prices"])
        deltas = np.diff(prices)
        gains = np.maximum(deltas, 0).sum() / self.rsi_period
        losses = -np.minimum(deltas, 0).sum() / self.rsi_period
        rs = gains / losses if losses != 0 else 0
        rsi = 100 - (100 / (1 + rs))
        self.rsi_values[stock] = rsi

        last_action = self.stocks_data[stock]["last_action"]
        entry_price = self.stocks_data[stock]["entry_price"]

        # Check for exit condition based on profit target
        if entry_price is not None:
            if last_action == "BUY" and (current_price >= entry_price * (1 + self.profit_target)):
                self.stocks_data[stock]["last_action"] = "SELL"
                self.stocks_data[stock]["entry_price"] = None
                logging.info(f"{stock}: Profit target reached for BUY. Exiting at {current_price}")
                return "SELL", current_price
            elif last_action == "SELL" and (current_price <= entry_price * (1 - self.profit_target)):
                self.stocks_data[stock]["last_action"] = "BUY"
                self.stocks_data[stock]["entry_price"] = None
                logging.info(f"{stock}: Profit target reached for SELL. Exiting at {current_price}")
                return "BUY", current_price

        # Check for entry condition based on RSI
        if (rsi < self.entry_rsi_low and last_action != "BUY") or (rsi > self.entry_rsi_high and last_action != "SELL"):
            action = "BUY" if rsi < self.entry_rsi_low else "SELL"
            self.stocks_data[stock]["last_action"] = action
            self.stocks_data[stock]["entry_price"] = current_price
            logging.info(f"{stock}: RSI {rsi} triggered a {action} action at price {current_price}")
            return action, current_price

        logging.info(f"{stock}: RSI {rsi} did not trigger any action. Last action was {last_action}")
        return None
