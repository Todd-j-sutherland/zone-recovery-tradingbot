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
from get_market_data import GetMarketData
from zone_recovery_logic import ZoneRecoveryLogic

class ZoneRecoveryBot(EWrapper, EClient):
    def __init__(self, tickers, metadata_file='stock_metadata.json'):
        EClient.__init__(self, self)
        self.metadata_file = metadata_file
        self.market_data_service = GetMarketData()
        self.data_update_interval = 60
        self.running = True
        self.stocks_to_check = self.load_and_update_metadata(tickers)
        self.logic = ZoneRecoveryLogic(self.stocks_to_check.copy())

    def load_and_update_metadata(self, tickers):
        """ Load and update stock metadata from a file based on provided tickers and scanned stocks. """
        if os.path.exists(self.metadata_file):
            try:
                with open(self.metadata_file, 'r') as file:
                    stocks_data = json.load(file)
            except json.JSONDecodeError:
                logging.error("JSON file is empty or corrupt. Initializing with an empty dictionary.")
                stocks_data = {}
        else:
            stocks_data = {}

        # Get stocks from scanner and merge with manually added tickers
        scanned_stocks = self.market_data_service.filter_stocks_by_price()
        combined_tickers = tickers + [stock for stock in scanned_stocks if stock not in tickers]

        # Update the metadata to reflect the combined list of tickers
        updated_stocks_data = {ticker: stocks_data.get(ticker, {"fetched": False, "prices": []}) for ticker in combined_tickers}
        self.save_metadata(updated_stocks_data)
        return updated_stocks_data

    def save_metadata(self, stocks_data):
        """ Save stock metadata to a file. """
        with open(self.metadata_file, 'w') as file:
            json.dump(stocks_data, file, indent=4)

    def start(self):
        self.connect("127.0.0.1", 7496, clientId=123)
        thread = threading.Thread(target=self.run)
        thread.start()
        self.waitForConnection()
        self.fetch_data_periodically()

    def waitForConnection(self):
        while not self.isConnected():
            time.sleep(1)

    def fetch_data_periodically(self):
        while self.running:
            try:
                for stock, info in self.stocks_to_check.items():
                    if not info["fetched"]:
                        # Fetch initial data including timestamps
                        initial_data = self.market_data_service.fetch_initial_data(stock, "1min", 30)
                        # Update the price list and mark as fetched
                        self.stocks_to_check[stock]["prices"].extend([price for price, _ in initial_data])
                        self.stocks_to_check[stock]["timestamps"] = [time for _, time in initial_data]
                        self.stocks_to_check[stock]["fetched"] = True
                        self.save_metadata(self.stocks_to_check)
                    # Continue to fetch latest price and update
                    price, timestamp = self.market_data_service.fetch_latest_price(stock, "1min")
                    if price and (not self.stocks_to_check[stock]['timestamps'] or timestamp != self.stocks_to_check[stock]['timestamps'][-1]):
                        self.stocks_to_check[stock]['prices'].append(price)
                        self.stocks_to_check[stock]['timestamps'].append(timestamp)
                        self.save_metadata(self.stocks_to_check)
                        result = self.logic.update_price(stock, price)
                        if result:
                            trade_type, current_price = result
                            print(result)
                            # self.trigger_trade(stock, trade_type, 1, current_price)
                time.sleep(self.data_update_interval)
            except KeyboardInterrupt:
                self.stop()
            except Exception as e:
                logging.error(f"An error occurred: {e}")

    def trigger_trade(self, symbol, trade_type, quantity, current_price):
        contract = self.create_contract(symbol)
        order = self.create_order(trade_type, quantity, current_price)
        self.placeOrder(self.nextOrderId, contract, order)
        self.nextOrderId += 1

    def create_contract(self, symbol):
        contract = Contract()
        contract.symbol = symbol
        contract.secType = "STK"  # Assuming stocks; adjust as necessary for other security types
        contract.currency = "USD"
        contract.exchange = "SMART"  # Ensure this matches the requirements of your trading strategy
        return contract

    def create_order(self, action, quantity, current_price):
        order = Order()
        order.action = action
        order.orderType = "LMT"
        order.totalQuantity = quantity
        order.lmtPrice = current_price
        order.tif = "GTC"
        return order

    def stop(self):
        self.running = False
        self.disconnect()
        logging.info("Disconnected and stopped successfully.")

def main():
    parser = argparse.ArgumentParser(description='Run the Zone Recovery Trading Bot with specified stock tickers.')
    parser.add_argument('tickers', nargs='+', help='List of stock tickers to monitor')
    args = parser.parse_args()

    app = ZoneRecoveryBot(args.tickers)
    app.start()

if __name__ == "__main__":
    main()
