import numpy as np
from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
from ibapi.order import Order

class ZoneRecoveryBot(EWrapper, EClient):
    def __init__(self):
        EClient.__init__(self, self)
        self.nextOrderId = None
        self.entry_price = None
        self.initial_order_filled = False
        self.zones = [-0.01, 0.01]  # Example zones
        self.rsi_period = 14  # Typical RSI period
        self.entry_rsi_low = 30
        self.entry_rsi_high = 70
        self.historical_data = []  # To store historical close prices for RSI calculation

    def error(self, reqId, errorCode, errorString, extraInfo):
        print("Error:", reqId, errorCode, errorString, extraInfo)

    def nextValidId(self, orderId: int):
        super().nextValidId(orderId)
        self.nextOrderId = orderId
        self.request_historical_data()

    def request_historical_data(self):
        contract = self.create_contract("TSLY", "STK", "SMART", "USD")
        # Request daily data for the last 30 days
        self.reqHistoricalData(2001, contract, '', '30 D', '1 day', 'MIDPOINT', 1, 1, False, [])

    def historicalData(self, reqId, bar):
        self.historical_data.append(bar.close)
        if len(self.historical_data) == 30:
            self.calculate_rsi()
            self.start_trading()

    def calculate_rsi(self):
        prices = np.array(self.historical_data)
        deltas = np.diff(prices)
        gains = deltas[deltas >= 0].sum() / self.rsi_period
        losses = -deltas[deltas < 0].sum() / self.rsi_period
        rs = gains / losses
        rsi = 100 - 100 / (1 + rs)
        self.current_rsi = rsi
        print("Initial RSI calculated:", self.current_rsi)

    def start_trading(self):
        if self.current_rsi < self.entry_rsi_low:
            print("RSI indicates oversold condition. Placing buy order.")
            self.open_initial_trade()
        else:
            print("Market conditions not favorable for entry based on RSI.")

    def open_initial_trade(self):
        contract = self.create_contract("TSLY", "STK", "SMART", "USD")
        order = self.create_order("BUY", 1, "MKT")
        self.placeOrder(self.nextOrderId, contract, order)
        self.nextOrderId += 1

    def request_market_data(self):
        contract = self.create_contract("TSLY", "STK", "SMART", "USD")
        self.reqRealTimeBars(1001, contract, 5, "MIDPOINT", True, [])

    def realTimeBar(self, reqId, time, open, high, low, close, volume, wap, count):
        print(f"Real-time bar data: Close price = {close}")
        self.historical_data.append(close)
        self.historical_data = self.historical_data[-self.rsi_period:]  # keep only the necessary data
        self.calculate_rsi()
        self.check_zones_and_trade(close)

    def check_zones_and_trade(self, current_price):
        if not self.initial_order_filled:
            return  # Do not trade until the initial order is filled
        for zone in self.zones:
            if (zone < 0 and current_price <= self.entry_price * (1 + zone)) or \
               (zone > 0 and current_price >= self.entry_price * (1 + zone)):
                self.open_additional_trade(zone)

    def open_additional_trade(self, zone):
        contract = self.create_contract("TSLY", "STK", "SMART", "USD")
        action = "BUY" if zone < 0 else "SELL"
        qty = 1
        price = self.entry_price * (1 + zone)
        order = self.create_order(action, qty, "LMT", price)
        self.placeOrder(self.nextOrderId, contract, order)
        self.nextOrderId += 1

    def execDetails(self, reqId, contract, execution):
        print("Order executed: ExecId:", execution.execId, "Price:", execution.price, "Qty:", execution.shares)
        if not self.initial_order_filled:
            self.entry_price = execution.price
            self.initial_order_filled = True

    def create_contract(self, symbol, sec_type, exchange, currency):
        contract = Contract()
        contract.symbol = symbol
        contract.secType = sec_type
        contract.exchange = exchange
        contract.currency = currency
        return contract

    def create_order(self, action, quantity, order_type, price=None):
        order = Order()
        order.action = action
        order.totalQuantity = quantity
        order.orderType = order_type
        if price is not None:
            order.lmtPrice = price
        return order

def main():
    app = ZoneRecoveryBot()
    app.connect("127.0.0.1", 7496, clientId=123)
    app.run()

if __name__ == "__main__":
    main()
