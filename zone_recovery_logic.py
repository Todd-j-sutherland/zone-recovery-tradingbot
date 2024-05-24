import numpy as np
import logging

from utils import calculate_rsi

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class ZoneRecoveryLogic:
    def __init__(self, rsi_period=14, entry_rsi_low=30, entry_rsi_high=70, profit_target=5, max_trades=5):
        self.rsi_period = rsi_period
        self.entry_rsi_low = entry_rsi_low
        self.entry_rsi_high = entry_rsi_high
        self.profit_target = profit_target  # 5% profit target
        self.max_trades = max_trades

    def calculate_rsi_and_check_profit(self, stock_data, stock, current_price):
        prices = np.array(stock_data["prices"])
        rsi = calculate_rsi(prices, self.rsi_period)

        trade_count = len(stock_data['long']) + len(stock_data['short'])

        total_profit = self.calculate_percentage_profit(stock_data['long'], stock_data['short'], current_price)

        if total_profit >= self.profit_target or trade_count >= self.max_trades:
            stock_data['long'] = []
            stock_data['short'] = []
            logging.info(f"{stock}: Closing all positions with profit {total_profit * 100}%")
            return "CLOSE_ALL", current_price, total_profit

        if rsi < self.entry_rsi_low:
            logging.info(f"{stock}: RSI {rsi} triggered a BUY action at price {current_price}")
            return "BUY", current_price, total_profit

        if rsi > self.entry_rsi_high:
            logging.info(f"{stock}: RSI {rsi} triggered a SELL action at price {current_price}")
            return "SELL", current_price, total_profit

        return None

    def calculate_percentage_profit(self, long_positions, short_positions, current_price):
        """Calculate the percentage profit based on initial investment and current market price."""
        # Calculate initial investment and profit for long positions
        long_initial = sum(pos['price'] * pos['qty'] for pos in long_positions)
        long_profit = sum((current_price - pos['price']) * pos['qty'] for pos in long_positions )
        
        # Calculate initial investment and profit for short positions
        short_initial = sum(pos['price'] * pos['qty'] for pos in short_positions)
        short_profit = sum((pos['price'] - current_price) * pos['qty'] for pos in short_positions)

        # Total initial investment and total profit
        total_initial = long_initial + short_initial
        total_profit = long_profit + short_profit

        return (total_profit / total_initial * 100) if total_initial != 0 else 0
