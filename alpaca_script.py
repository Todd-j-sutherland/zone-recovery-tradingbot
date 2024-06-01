import os
import time
from alpaca.trading import TradingClient
from ib_insync import OrderState
from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce, OrderStatus

# Retrieve API keys from environment variables
alpaca_api_key = os.getenv('ALPACA_API_KEY')
alpaca_secret_key = os.getenv('ALPACA_SECRET_KEY')


# Initialize your trading client with your API credentials
trading_client = TradingClient(alpaca_api_key, alpaca_secret_key, paper=True)

# Create the order request
market_order_data = LimitOrderRequest(
    symbol="AAPL",
    qty=1,
    limit_price=193,
    side=OrderSide.BUY,
    time_in_force=TimeInForce.DAY
)

# Submit the order
market_order = trading_client.submit_order(order_data=market_order_data)


def monitor_alpaca_order(order, symbol, trading_client):
    """Monitor the Alpaca order status."""
    try:
        # Poll the order status until it is finalized ('filled', 'rejected', or 'canceled')
        while True:
            updated_order = trading_client.get_order_by_id(order.id)
            if updated_order.status in [OrderStatus.FILLED, OrderStatus.REJECTED, OrderStatus.CANCELED]:
                if updated_order.status == OrderStatus.FILLED:
                    print('Order filled')
                else:
                    print(f"Order for {symbol} was {updated_order.status.lower()}.")
                break  # Exit the loop once the order is finalized
            time.sleep(1)  # Sleep to prevent excessive API calls
    except Exception as e:
        print(f"Error monitoring Alpaca order: {e}")

monitor_alpaca_order(market_order, 'AAPL', trading_client)
print("Order submitted:", market_order)
