import numpy as np
import logging

from utils import calculate_rsi

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class ZoneRecoveryLogic:
    def __init__(self, stocks_data, rsi_period=14, entry_rsi_low=30, entry_rsi_high=70, profit_target=0.05, max_trades=5):
        self.stocks_data = stocks_data
        self.rsi_period = rsi_period
        self.entry_rsi_low = entry_rsi_low
        self.entry_rsi_high = entry_rsi_high
        self.profit_target = profit_target  # 5% profit target
        self.max_trades = max_trades
        self.positions = {stock: {'long': [], 'short': []} for stock in stocks_data}

    def update_price(self, stock, price):
        self.stocks_data[stock]["prices"].append(price)
        if len(self.stocks_data[stock]["prices"]) > self.rsi_period:
            self.stocks_data[stock]["prices"].pop(0)
        if len(self.stocks_data[stock]["prices"]) >= self.rsi_period:
            return self.calculate_rsi_and_check_profit(stock, price)
        return None

    def calculate_rsi_and_check_profit(self, stock, current_price):
        prices = np.array(self.stocks_data[stock]["prices"])
        rsi = calculate_rsi(prices, self.rsi_period)

        current_positions = self.positions[stock]
        trade_count = len(current_positions['long']) + len(current_positions['short'])

        total_profit = self.calculate_total_profit(stock, current_price)

        if total_profit >= self.profit_target:
            self.positions[stock] = {'long': [], 'short': []}
            logging.info(f"{stock}: Closing all positions with profit {total_profit * 100}%")
            return "CLOSE_ALL", current_price

        if trade_count >= self.max_trades:
            return None

        if rsi < self.entry_rsi_low:
            current_positions['long'].append({"price": current_price, "qty": 1})
            logging.info(f"{stock}: RSI {rsi} triggered a BUY action at price {current_price}")
            return "BUY", current_price

        if rsi > self.entry_rsi_high:
            current_positions['short'].append({"price": current_price, "qty": 1})
            logging.info(f"{stock}: RSI {rsi} triggered a SELL action at price {current_price}")
            return "SELL", current_price

        return None

    def calculate_total_profit(self, stock, current_price):
        long_positions = self.positions[stock]['long']
        short_positions = self.positions[stock]['short']

        long_profit = sum([(current_price - pos['price']) * pos['qty'] for pos in long_positions])
        short_profit = sum([(pos['price'] - current_price) * pos['qty'] for pos in short_positions])

        total_profit = long_profit + short_profit
        return total_profit
