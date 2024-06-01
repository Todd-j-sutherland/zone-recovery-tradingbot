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
from utils import calculate_rsi
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
        self.total_session_profit = 0

    def load_and_update_metadata(self, tickers):
        stocks_data = {}
        scanned_stocks = [candidates for candidates, _ in self.market_data_service.get_potential_candidates()]
        combined_tickers = tickers + [stock for stock in scanned_stocks if stock not in tickers]
        updated_stocks_data = {ticker: stocks_data.get(ticker, {"fetched": False, "prices": [], "volumes": [], "long": [], "short": []}) for ticker in combined_tickers}
        return updated_stocks_data

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
                        self.stocks_to_check[stock]["previous_rsi"] = calculate_rsi(self.stocks_to_check[stock]["prices"], self.logic.rsi_period)
                    if len(self.stocks_to_check[stock]["prices"]) >= self.logic.rsi_period:
                        price, timestamp, volume = self.market_data_service.fetch_latest_price(stock, "1min")
                        if price and (not self.stocks_to_check[stock]['timestamps'] or timestamp != self.stocks_to_check[stock]['timestamps'][-1]):
                            self.stocks_to_check[stock]['prices'].append(price)
                            self.stocks_to_check[stock]['timestamps'].append(timestamp)
                            self.stocks_to_check[stock]["volumes"].append(volume)
                            self.stocks_to_check[stock]['prices'].pop(0)
                            self.stocks_to_check[stock]['timestamps'].pop(0)
                            self.stocks_to_check[stock]['volumes'].pop(0)
                            self.check_and_execute_trades(stock, price)
                    else:
                        logging.warning(f"Did not find enough initial data for stock: {stock}")
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
                self.close_all_positions(stock, price)
                self.total_session_profit += profit
            elif trade_type == 'BUY':
                self.trigger_trade(stock, trade_type, 1, price, True)
            elif trade_type == 'SELL':
                self.trigger_trade(stock, trade_type, 1, price, False) 

    def close_all_positions(self, stock, current_price):
        """Close all positions for the given stock symbol."""
        # Close positions if they exist in 'long' or 'short' states
        for position_type in ['long', 'short']:
            if self.stocks_to_check[stock][position_type]:
                total_qty = sum(item['qty'] for item in self.stocks_to_check[stock][position_type])
                order_type = "SELL" if position_type == 'long' else "BUY"
                self.trigger_trade(stock, order_type, total_qty, current_price, alpaca=position_type == 'long')

        # Reset stock data after closing positions
        self.reset_stock_data(stock)

    def reset_stock_data(self, stock):
        """Reset historical and positional data for a stock."""
        fields = ['prices', 'timestamps', 'volumes', 'long', 'short']
        for field in fields:
            self.stocks_to_check[stock][field] = []
        self.stocks_to_check[stock]['fetched'] = False

    def trigger_trade(self, symbol, trade_type, quantity, current_price, alpaca=False):
        """Trigger a trade with the specified parameters."""
        symbol = symbol.upper()
        if alpaca:
            order_data = MarketOrderRequest(
                symbol=symbol,
                qty=quantity,
                side=OrderSide.BUY if trade_type == "BUY" else OrderSide.SELL,
                time_in_force=TimeInForce.GTC
            ) if current_price is None else LimitOrderRequest(
                symbol=symbol,
                qty=quantity,
                side=OrderSide.BUY if trade_type == "BUY" else OrderSide.SELL,
                limit_price=current_price,
                time_in_force=TimeInForce.GTC
            )
            order = self.alpaca_trading_client.submit_order(order_data)
            # Check order status and handle accordingly
            self.monitor_alpaca_order(order, symbol)
        else:
            self.ib_client.reqIds(-1)  # Request a new order ID
            while self.ib_client.nextValidOrderId is None:
                time.sleep(0.1)
            order_id = self.ib_client.nextValidOrderId
            contract = self.create_contract(symbol)
            order = self.create_order(trade_type, quantity, current_price)
            self.ib_client.placeOrder(order_id, contract, order)
            # Monitoring and handling of the order status after placing the order
            self.monitor_ib_order(order_id, symbol)

    def monitor_ib_order(self, order_id, symbol):
        """Monitor IB order and handle its execution status."""
        filled = self.ib_client.waitForOrderFill(order_id)
        if filled:
            order_details = self.ib_client.order_statuses.get(order_id, {})
            self.handle_filled_order(order_details, False, symbol)
        else:
            logging.info(f"Order for {symbol} was rejected")

    def monitor_alpaca_order(self, order, symbol):
        """Monitor the Alpaca order status."""
        try:
            # Poll the order status until it is finalized ('filled', 'rejected', or 'canceled')
            while True:
                updated_order = self.alpaca_trading_client.get_order_by_id(order.id)
                if updated_order.status in [OrderStatus.FILLED, OrderStatus.REJECTED, OrderStatus.CANCELED]:
                    if updated_order.status == OrderStatus.FILLED:
                        self.handle_filled_order(updated_order, True, symbol)
                    else:
                        logging.info(f"Order for {symbol} was rejected")
                    break  # Exit the loop once the order is finalized
                time.sleep(1)  # Sleep to prevent excessive API calls
        except Exception as e:
            logging.error(f"Error monitoring Alpaca order: {e}")

    def handle_filled_order(self, order, alpaca, symbol):
        """Handle filled orders."""
        if alpaca:
            # Accessing Alpaca order object attributes directly
            price = order.filled_avg_price if order.filled_avg_price else order.limit_price
            qty = order.filled_qty
            logging.info(f"Order for {symbol} filled at {price} with quantity {qty}")
            self.stocks_to_check[symbol]["long"].append({"price": price, "qty": qty})
        else:
            # Assuming 'order' is a dictionary with keys for IB orders
            price = order.get('avgFillPrice')
            qty = order.get('filled')
            logging.info(f"Order for {symbol} filled at {price}")
            self.stocks_to_check[symbol]["short"].append({"price": price, "qty": qty})

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
