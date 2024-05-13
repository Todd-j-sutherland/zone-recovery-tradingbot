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
        self.logic = ZoneRecoveryLogic(self.stocks_to_check)

    def load_and_update_metadata(self, tickers):
        """ Load and update stock metadata from a file based on provided tickers. """
        if os.path.exists(self.metadata_file):
            with open(self.metadata_file, 'r') as file:
                stocks_data = json.load(file)
        else:
            stocks_data = {}

        # Update the metadata to reflect only the tickers provided
        updated_stocks_data = {ticker: stocks_data.get(ticker, {"fetched": False, "prices": []}) for ticker in tickers}
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
                        # Fetch initial data
                        data = self.market_data_service.fetch_initial_data(stock, "1min", 30)
                        self.stocks_to_check[stock]["prices"].extend(data)
                        self.stocks_to_check[stock]["fetched"] = True
                        self.save_metadata(self.stocks_to_check)  # Corrected call
                    # Fetch latest price and update periodically
                    price = self.market_data_service.fetch_latest_price(stock, "1min")
                    if price:
                        self.stocks_to_check[stock]["prices"].append(price)
                        self.save_metadata(self.stocks_to_check)  # Corrected call
                        result = self.logic.update_price(stock, price)
                        if result:
                            trade_type, current_price = result
                            self.trigger_trade(stock, trade_type, 1, current_price)
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
        return Contract(symbol=symbol, secType="STK", currency="USD", exchange="SMART")

    def create_order(self, action, quantity, current_price):
        return Order(action=action, orderType="LMT", totalQuantity=quantity, lmtPrice=current_price, tif="GTC")

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
