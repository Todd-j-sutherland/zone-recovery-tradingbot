import numpy as np
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class ZoneRecoveryLogic:
    def __init__(self, stocks_data, rsi_period=14, entry_rsi_low=30, entry_rsi_high=70, profit_target=0.05, max_trades=5):
        self.stocks_data = stocks_data
        self.rsi_period = rsi_period
        self.entry_rsi_low = entry_rsi_low
        self.entry_rsi_high = entry_rsi_high
        self.profit_target = profit_target  # 5% profit target
        self.rsi_values = {}
        self.orders = {}  # Stores order details
        self.positions = {}  # Tracks open positions
        self.max_trades = max_trades
        self.trade_count = {stock: 0 for stock in stocks_data}  # Track number of trades per stock

        # Initialize data structures
        for stock in stocks_data:
            self.stocks_data[stock].setdefault("last_action", None)
            self.stocks_data[stock].setdefault("entry_price", None)
            self.positions[stock] = {'quantity': 0, 'avg_price': 0}
            logging.debug(f"Initialized {stock} with empty last action and no entry price.")

    def update_position(self, response):
        """Update or close positions based on filled orders."""
        symbol = response['contract']['symbol']
        action = response['order']['action']
        filled = response['filled']
        avg_fill_price = response['avgFillPrice']

        if action == 'BUY':
            total_quantity = self.positions[symbol]['quantity'] + filled
            total_cost = self.positions[symbol]['avg_price'] * self.positions[symbol]['quantity'] + filled * avg_fill_price
            self.positions[symbol]['quantity'] = total_quantity
            self.positions[symbol]['avg_price'] = total_cost / total_quantity
        elif action == 'SELL':
            total_quantity = self.positions[symbol]['quantity'] - filled
            if total_quantity <= 0:
                self.positions[symbol] = {'quantity': 0, 'avg_price': 0}
            else:
                total_cost = self.positions[symbol]['avg_price'] * self.positions[symbol]['quantity'] - filled * avg_fill_price
                self.positions[symbol]['quantity'] = total_quantity
                self.positions[symbol]['avg_price'] = total_cost / total_quantity if total_quantity != 0 else 0
        logging.info(f"Position updated for {symbol}: {self.positions[symbol]}")

    def update_price(self, stock, price):
        self.stocks_data[stock]["prices"].append(price)
        if len(self.stocks_data[stock]["prices"]) > self.rsi_period:
            self.stocks_data[stock]["prices"].pop(0)
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

        # Check for profit targets or new entry signals
        if entry_price is not None and ((last_action == "BUY" and current_price >= entry_price * (1 + self.profit_target)) or
                                       (last_action == "SELL" and current_price <= entry_price * (1 - self.profit_target))):
            self.stocks_data[stock]["last_action"] = None
            self.stocks_data[stock]["entry_price"] = None
            self.trade_count[stock] = 0  # Reset trade count on position close
            action = "SELL" if last_action == "BUY" else "BUY"
            logging.info(f"{stock}: Profit target reached or stopped at {current_price}. Closing position with {action}.")
            return action, current_price, True  # Indicate position is closed

        if (rsi < self.entry_rsi_low and last_action != "BUY") or (rsi > self.entry_rsi_high and last_action != "SELL"):
            self.stocks_data[stock]["last_action"] = "BUY" if rsi < self.entry_rsi_low else "SELL"
            self.stocks_data[stock]["entry_price"] = current_price
            logging.info(f"{stock}: RSI {rsi} triggered a {self.stocks_data[stock]['last_action']} action at price {current_price}")
            return self.stocks_data[stock]['last_action'], current_price, False

        # Handle the scenario where the trade is not profitable and we need to counter the position
        if last_action is not None and entry_price is not None:
            if last_action == "BUY" and current_price <= entry_price * (1 - self.profit_target) and self.trade_count[stock] < self.max_trades:
                self.trade_count[stock] += 1
                logging.info(f"{stock}: Long position turned negative. Countering with a SELL at price {current_price}.")
                return "SELL", current_price, False
            elif last_action == "SELL" and current_price >= entry_price * (1 + self.profit_target) and self.trade_count[stock] < self.max_trades:
                self.trade_count[stock] += 1
                logging.info(f"{stock}: Short position turned negative. Countering with a BUY at price {current_price}.")
                return "BUY", current_price, False

        return None