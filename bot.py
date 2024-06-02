import os
import time
from ib_insync import IB, Stock, MarketOrder, LimitOrder
import logging
import argparse
from alpaca.trading import TradingClient
from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce, OrderStatus
from get_market_data import GetMarketData
from utils import calculate_rsi
from zone_recovery_logic import ZoneRecoveryLogic
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class IBClient:
    def __init__(self, host='127.0.0.1', port=4002, client_id=123):
        self.ib = IB()
        self.ib.connect(host, port, clientId=client_id)

    def verify_contract(self, contract):
        logging.info(f"Verifying contract for symbol: {contract.symbol}, exchange: {contract.exchange}, currency: {contract.currency}")
        contract_details = self.ib.reqContractDetails(contract)
        if not contract_details:
            logging.error(f"No contract details found for {contract.symbol} on {contract.exchange}")
            return None
        logging.info(f"Contract details found: {contract_details[0].contract}")
        return contract_details[0].contract

    def find_correct_exchange(self, symbol, exchanges=['SMART', 'NASDAQ', 'NYSE', 'AMEX']):
        for exchange in exchanges:
            contract = Stock(symbol, exchange, 'USD')
            verified_contract = self.verify_contract(contract)
            if verified_contract:
                logging.info(f"Found valid contract for {symbol} on {exchange}")
                return verified_contract
        logging.error(f"No valid contract found for {symbol} on any exchange.")
        return None

    def place_order(self, symbol, quantity, limit_price, action, is_market):
        contract = self.find_correct_exchange(symbol)
        if contract is None:
            return None
        
        order = MarketOrder(action, quantity) if is_market else LimitOrder(action, quantity, limit_price)
        trade = self.ib.placeOrder(contract, order)
        return trade

    def monitor_order(self, trade):
        while not trade.isDone():
            self.ib.sleep(1)  # Sleeps to prevent excessive updates, respects API limits
            logging.info(f"Current order status: {trade.orderStatus.status}")
        logging.info(f'Order done with status {trade.orderStatus.status}')
        return trade.order

    def stop(self):
        self.ib.disconnect()

class AlpacaClient:
    def __init__(self, is_paper=True):
        self.api_key = os.getenv('ALPACA_API_KEY')
        self.secret_key = os.getenv('ALPACA_SECRET_KEY')
        self.client = TradingClient(self.api_key, self.secret_key, paper=is_paper)

    def place_order(self, symbol, quantity, action, is_market, limit_price=None):
        side = OrderSide.BUY if action == "BUY" else OrderSide.SELL
        if is_market:
            order_data = MarketOrderRequest(
                symbol=symbol,
                qty=quantity,
                side=side,
                time_in_force=TimeInForce.GTC
            )
        else:
            order_data = LimitOrderRequest(
                symbol=symbol,
                qty=quantity,
                side=side,
                limit_price=limit_price,
                time_in_force=TimeInForce.GTC
            )
        order = self.client.submit_order(order_data=order_data)
        return order

    def monitor_order(self, order):
        while True:
            order = self.client.get_order_by_id(order.id)
            if order.status in [OrderStatus.FILLED, OrderStatus.REJECTED, OrderStatus.CANCELED]:
                if order.status == OrderStatus.FILLED:
                    print(f"Order for {order.symbol} filled.")
                else:
                    print(f"Order for {order.symbol} was {order.status.lower()}.")
                break
            time.sleep(1)
        return order

class ZoneRecoveryBot:
    def __init__(self, tickers, ib_client, alpaca_trading_client):
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
            action, price, profit = result
            if action == "CLOSE_ALL":
                self.close_all_positions(stock, price)
                self.total_session_profit += profit
            elif action == 'BUY':
                self.trigger_trade(stock, action, 1, price, True)
            elif action == 'SELL':
                self.trigger_trade(stock, action, 1, price, False) 

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

    def trigger_trade(self, symbol, action, quantity, current_price, alpaca=False):
        """Trigger a trade with the specified parameters."""
        symbol = symbol.upper()
        if alpaca:
            order = self.alpaca_trading_client.place_order(self, symbol, quantity, action, False, limit_price=current_price)
            order = self.alpaca_trading_client.monitor_order(order)
            if order.status == OrderStatus.FILLED:
                self.handle_filled_order(order, True, symbol)
            else:
                logging.info(f'Alpaca order was not filled. Status was {order.status}')
        else:
            trade = self.ib_client.place_order(symbol, quantity, current_price, action, False)
            if not trade:
                logging.info(f'Stock {symbol} can\'t be traded, skipping.')
                return
            order = self.ib_client.monitor_order(trade)
            if trade.orderStatus.status == 'Filled':
                self.handle_filled_order(order, False, symbol)
            else:
                logging.info(f'IB Order was not filled. Status was {trade.orderStatus.status}')

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
            logging.info(f"Order for {symbol} filled at {price} with quantity {qty}")
            self.stocks_to_check[symbol]["short"].append({"price": price, "qty": qty})

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
