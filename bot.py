import json
import os
import time
import threading
import logging
import argparse
from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
from ibapi.order import Order
import alpaca_trade_api as tradeapi
from get_market_data import GetMarketData
from zone_recovery_logic import ZoneRecoveryLogic
import numpy as np
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class IBClient(EWrapper, EClient):
    def __init__(self, client_id):
        EClient.__init__(self, self)
        self.client_id = client_id
        self.nextValidOrderId = None

    def nextValidId(self, orderId):
        self.nextValidOrderId = orderId

    def start(self):
        self.connect("127.0.0.1", 7496, clientId=self.client_id)
        thread = threading.Thread(target=self.run)
        thread.start()
        self.waitForConnection()

    def waitForConnection(self):
        while not self.isConnected():
            time.sleep(1)

    def stop(self):
        self.disconnect()

class ZoneRecoveryBot:
    def __init__(self, tickers, ib_client, alpaca_client, metadata_file='stock_metadata.json'):
        self.metadata_file = metadata_file
        self.market_data_service = GetMarketData()
        self.data_update_interval = 60
        self.running = True
        self.stocks_to_check = self.load_and_update_metadata(tickers)
        self.logic = ZoneRecoveryLogic(self.stocks_to_check.copy())
        self.ib_client = ib_client
        self.alpaca_client = alpaca_client

    def load_and_update_metadata(self, tickers):
        if os.path.exists(self.metadata_file):
            try:
                with open(self.metadata_file, 'r') as file:
                    stocks_data = json.load(file)
            except json.JSONDecodeError:
                logging.error("JSON file is empty or corrupt. Initializing with an empty dictionary.")
                stocks_data = {}
        else:
            stocks_data = {}

        scanned_stocks = [candidates for candidates, _ in self.market_data_service.get_potential_candidates()]
        combined_tickers = tickers + [stock for stock in scanned_stocks if stock not in tickers]
        updated_stocks_data = {ticker: stocks_data.get(ticker, {"fetched": False, "prices": [], "volumes": []}) for ticker in combined_tickers}
        self.save_metadata(updated_stocks_data)
        return updated_stocks_data

    def save_metadata(self, stocks_data):
        with open(self.metadata_file, 'w') as file:
            json.dump(stocks_data, file, indent=4)

    def start(self):
        self.ib_client.start()
        self.fetch_data_periodically()

    def fetch_data_periodically(self):
        while self.running:
            try:
                for stock, info in self.stocks_to_check.items():
                    if not info["fetched"]:
                        initial_data, volumes = self.market_data_service.fetch_initial_data(stock, "1day", 30, "delayed", "TIME_SERIES_DAILY")
                        self.stocks_to_check[stock]["prices"].extend([price for price, _ in initial_data])
                        self.stocks_to_check[stock]["timestamps"] = [time for _, time in initial_data]
                        self.stocks_to_check[stock]["volumes"].extend(volumes)
                        self.stocks_to_check[stock]["fetched"] = True
                        self.save_metadata(self.stocks_to_check)
                    price, timestamp = self.market_data_service.fetch_latest_price(stock, "1Min")
                    if price and (not self.stocks_to_check[stock]['timestamps'] or timestamp != self.stocks_to_check[stock]['timestamps'][-1]):
                        self.stocks_to_check[stock]['prices'].append(price)
                        self.stocks_to_check[stock]['timestamps'].append(timestamp)
                        self.stocks_to_check[stock]['prices'].pop(0)
                        self.stocks_to_check[stock]['timestamps'].pop(0)
                        self.save_metadata(self.stocks_to_check)
                        self.check_and_execute_trades(stock, price)
                time.sleep(self.data_update_interval)
            except KeyboardInterrupt:
                self.stop()
            except Exception as e:
                logging.error(f"An error occurred: {e}")

    def check_and_execute_trades(self, stock, current_price):
        """Check if a trade should be executed based on current price and profit conditions."""
        result = self.logic.update_price(stock, current_price)
        if result:
            trade_type, price, position_closed = result
            if position_closed:
                self.close_all_positions(stock)
            else:
                self.trigger_trade(stock, trade_type, 1, price)

    def close_all_positions(self, stock):
        """Close all positions for the given stock symbol."""
        # Close long position if it exists
        if self.logic.positions[stock]['long']['quantity'] > 0:
            self.trigger_trade(stock, "SELL", self.logic.positions[stock]['long']['quantity'], None, alpaca=True)

        # Close short position if it exists
        if self.logic.positions[stock]['short']['quantity'] > 0:
            self.trigger_trade(stock, "BUY", self.logic.positions[stock]['short']['quantity'], None, alpaca=False)

        # Reset historical data for the stock when position is closed
        self.stocks_to_check[stock]["prices"] = []
        self.stocks_to_check[stock]["timestamps"] = []
        self.stocks_to_check[stock]["volumes"] = []

    def trigger_trade(self, symbol, trade_type, quantity, current_price, alpaca=False):
        """Trigger a trade with the specified parameters."""
        if alpaca:
            # Use Alpaca for long trades
            if trade_type == "BUY":
                self.alpaca_client.submit_order(
                    symbol=symbol,
                    qty=quantity,
                    side='buy',
                    type='market' if current_price is None else 'limit',
                    limit_price=current_price,
                    time_in_force='gtc'
                )
            else:
                self.alpaca_client.submit_order(
                    symbol=symbol,
                    qty=quantity,
                    side='sell',
                    type='market' if current_price is None else 'limit',
                    limit_price=current_price,
                    time_in_force='gtc'
                )
        else:
            # Use IB for short trades
            self.ib_client.reqIds(-1)  # Request a new order ID
            while self.ib_client.nextValidOrderId is None:
                time.sleep(0.1)

            order_id = self.ib_client.nextValidOrderId
            contract = self.create_contract(symbol)
            order = self.create_order(trade_type, quantity, current_price)
            self.ib_client.placeOrder(order_id, contract, order)
            self.ib_client.nextValidOrderId += 1

    def create_contract(self, symbol):
        contract = Contract()
        contract.symbol = symbol
        contract.secType = "STK"
        contract.currency = "USD"
        contract.exchange = "SMART"
        return contract

    def create_order(self, action, quantity, current_price):
        order = Order()
        order.action = action
        order.orderType = "LMT" if current_price else "MKT"
        order.totalQuantity = quantity
        if current_price:
            order.lmtPrice = current_price
        order.tif = "GTC"
        return order

    def stop(self):
        self.running = False
        self.ib_client.stop()
        logging.info("Disconnected and stopped successfully.")


def main():
    parser = argparse.ArgumentParser(description='Run the Zone Recovery Trading Bot with specified stock tickers.')
    parser.add_argument('tickers', nargs='+', help='List of stock tickers to monitor')
    args = parser.parse_args()

    # Load Alpaca credentials from environment variables
    alpaca_api_key = os.getenv('ALPACA_API_KEY')
    alpaca_secret_key = os.getenv('ALPACA_SECRET_KEY')
    alpaca_base_url = os.getenv('ALPACA_BASE_URL')

    # Initialize Alpaca client
    alpaca_client = tradeapi.REST(alpaca_api_key, alpaca_secret_key, alpaca_base_url, api_version='v2')
    
    # Initialize IB client
    ib_client = IBClient(client_id="123")

    # Initialize and start the trading bot
    app = ZoneRecoveryBot(args.tickers, ib_client, alpaca_client)
    app.identify_profitable_stocks()
    app.start()

if __name__ == "__main__":
    main()
