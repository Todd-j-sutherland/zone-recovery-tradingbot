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
from alpaca.trading import TradingClient
from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce, OrderStatus
from get_market_data import GetMarketData
from zone_recovery_logic import ZoneRecoveryLogic
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class IBClient(EWrapper, EClient):
    def __init__(self, client_id):
        EClient.__init__(self, self)
        self.client_id = client_id
        self.nextValidOrderId = None
        self.order_statuses = {}
        self.orders_filled = threading.Event()

    def nextValidId(self, orderId):
        self.nextValidOrderId = orderId

    def orderStatus(self, orderId, status, filled, remaining, avgFillPrice, permId, parentId, lastFillPrice, clientId, whyHeld, mktCapPrice):
        super().orderStatus(orderId, status, filled, remaining, avgFillPrice, permId, parentId, lastFillPrice, clientId, whyHeld, mktCapPrice)
        self.order_statuses[orderId] = {
            "status": status,
            "filled": filled,
            "remaining": remaining,
            "avgFillPrice": avgFillPrice
        }
        if status == 'Filled':
            self.orders_filled.set()  # Signal that the order is filled

    def start(self):
        self.connect("127.0.0.1", 4002, clientId=self.client_id)
        thread = threading.Thread(target=self.run)
        thread.start()
        self.waitForConnection()

    def waitForConnection(self):
        while not self.isConnected():
            time.sleep(1)

    def stop(self):
        self.disconnect()

    def waitForOrderFill(self, orderId, timeout=30):
        """ Wait for an order to be filled or until timeout. """
        is_filled = self.orders_filled.wait(timeout)
        if is_filled and self.order_statuses[orderId]['status'] == 'Filled':
            print(f"Order {orderId} fully filled.")
            return True
        else:
            print(f"Order {orderId} not filled. Status: {self.order_statuses[orderId]['status'] if orderId in self.order_statuses else 'Unknown'}")
            return False

class ZoneRecoveryBot:
    def __init__(self, tickers, ib_client, alpaca_trading_client, metadata_file='stock_metadata.json'):
        self.metadata_file = metadata_file
        self.market_data_service = GetMarketData()
        self.data_update_interval = 60
        self.running = True
        self.stocks_to_check = self.load_and_update_metadata(tickers)
        self.logic = ZoneRecoveryLogic()
        self.ib_client = ib_client
        self.alpaca_trading_client = alpaca_trading_client
        # store how much profit we are making for this session
        self.total_session_profit = 0

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
        updated_stocks_data = {ticker: stocks_data.get(ticker, {"fetched": False, "prices": [], "volumes": [], "long": [], "short": []}) for ticker in combined_tickers}
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
                    if len(self.stocks_to_check[stock]["prices"]) >= self.logic.rsi_period:
                        price, timestamp, volume = self.market_data_service.fetch_latest_price(stock, "1Min")
                        if price and (not self.stocks_to_check[stock]['timestamps'] or timestamp != self.stocks_to_check[stock]['timestamps'][-1]):
                            self.stocks_to_check[stock]['prices'].append(price)
                            self.stocks_to_check[stock]['timestamps'].append(timestamp)
                            self.stocks_to_check[stock]["volumes"].append(volume)
                            self.stocks_to_check[stock]['prices'].pop(0)
                            self.stocks_to_check[stock]['timestamps'].pop(0)
                            self.stocks_to_check[stock]['volumes'].pop(0)
                            self.check_and_execute_trades(stock, price)
                    else:
                        logging.warning(f"Did not find enough inital data for stock: {stock}")
                        self.stocks_to_check[stock]["fetched"] = False
                time.sleep(self.data_update_interval)
            except KeyboardInterrupt:
                self.stop()
            except Exception as e:
                logging.error(f"An error occurred: {e}")

    def check_and_execute_trades(self, stock, current_price):
        """Check if a trade should be executed based on current price and profit conditions."""
        result = self.logic.calculate_rsi_and_check_profit(self.stocks_to_check[stock], stock, current_price)
        if result:
            trade_type, price, profit = result
            if trade_type == "CLOSE_ALL":
                self.close_all_positions(stock, current_price)
            else:
                self.trigger_trade(stock, trade_type, 1, current_price)

    def close_all_positions(self, stock, current_price):
        """Close all positions for the given stock symbol."""
        # Close long position if it exists
        for _ in self.logic.positions[stock]['long']:
            self.trigger_trade(stock, "SELL", 1, current_price, alpaca=True)

        # Close short position if it exists
        for _ in self.logic.positions[stock]['short']:
            self.trigger_trade(stock, "BUY", 1, current_price, alpaca=False)

        # Reset historical data for the stock when position is closed
        self.stocks_to_check[stock]["prices"] = []
        self.stocks_to_check[stock]["timestamps"] = []
        self.stocks_to_check[stock]["volumes"] = []
        self.stocks_to_check[stock]["long"] = []
        self.stocks_to_check[stock]["short"] = []

    def trigger_trade(self, symbol, trade_type, quantity, current_price, alpaca=False):
        """Trigger a trade with the specified parameters."""
        if alpaca:
            # Use Alpaca for long trades
            if trade_type == "BUY":
                order_data = MarketOrderRequest(
                    symbol=symbol,
                    qty=quantity,
                    side=OrderSide.BUY,
                    time_in_force=TimeInForce.GTC
                ) if current_price is None else LimitOrderRequest(
                    symbol=symbol,
                    qty=quantity,
                    side=OrderSide.BUY,
                    limit_price=current_price,
                    time_in_force=TimeInForce.GTC
                )
            else:
                order_data = MarketOrderRequest(
                    symbol=symbol,
                    qty=quantity,
                    side=OrderSide.SELL,
                    time_in_force=TimeInForce.GTC
                ) if current_price is None else LimitOrderRequest(
                    symbol=symbol,
                    qty=quantity,
                    side=OrderSide.SELL,
                    limit_price=current_price,
                    time_in_force=TimeInForce.GTC
                )
            order = self.alpaca_trading_client.submit_order(order_data)
            
            # Monitor the order status
            order_status = self.monitor_alpaca_order(order)
            if order_status == OrderStatus.FILLED:
                self.handle_filled_order(order, True)
            elif order_status == OrderStatus.REJECTED:
                self.handle_rejected_order(order, True)
        else:
            # Use IB for short trades
            self.ib_client.reqIds(-1)  # Request a new order ID
            while self.ib_client.nextValidOrderId is None:
                time.sleep(0.1)

            order_id = self.ib_client.nextValidOrderId
            contract = self.create_contract(symbol)
            order = self.create_order(trade_type, quantity, current_price)
            self.ib_client.placeOrder(order_id, contract, order)

            # Monitor the order status
            order_status = self.monitor_ib_order(order_id)
            breakpoint()
            if order_status == 'Filled':
                self.handle_filled_order(order, False)
            elif order_status == 'Rejected':
                self.handle_rejected_order(order, False)

            self.ib_client.nextValidOrderId += 1

    def monitor_alpaca_order(self, order):
        while True:
            order_status = self.alpaca_trading_client.get_order(order.id).status
            if order_status in [OrderStatus.FILLED, OrderStatus.REJECTED, OrderStatus.CANCELED]:
                return order_status
            time.sleep(1)

    def monitor_ib_order(self, order_id):
        while True:
            order_status = self.ib_client.order_status(order_id)
            if order_status in ['Filled', 'Rejected', 'Cancelled']:
                return order_status
            time.sleep(1)

    def handle_filled_order(self, order, alpaca):
        """Handle filled orders."""
        logging.info(f"Order {order} filled")
        symbol = order.symbol
        price = order.filled_avg_price
        qty = order.qty

        if alpaca:
            self.stocks_to_check[symbol]["long"].append({"price": price, "qty": qty})
        else:
            self.stocks_to_check[symbol]["short"].append({"price": price, "qty": qty})

        self.save_metadata(self.stocks_to_check)

    def handle_rejected_order(self, order):
        """Handle rejected orders."""
        logging.info(f"Order {order} rejected")

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

    # Initialize Alpaca client
    alpaca_trading_client = TradingClient(alpaca_api_key, alpaca_secret_key)
    
    # Initialize IB client
    ib_client = IBClient(client_id="123")

    # Initialize and start the trading bot
    app = ZoneRecoveryBot(args.tickers, ib_client, alpaca_trading_client)
    app.start()

if __name__ == "__main__":
    main()
