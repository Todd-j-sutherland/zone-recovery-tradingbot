from ib_insync import IB, Stock, MarketOrder

def main():
    # Establish connection to Interactive Brokers TWS or Gateway
    ib = IB()
    ib.connect('127.0.0.1', 4002, clientId=123)  # Adjust the port and clientId as necessary

    try:
        # Define the contract: AAPL stock on the NASDAQ
        contract = Stock('AAPL', 'SMART', 'USD')

        # Create a market order: buying 10 shares of AAPL
        order = MarketOrder('BUY', 10)

        # Submit the order
        trade = ib.placeOrder(contract, order)

        # Monitor the order until it is filled
        print("Monitoring order...")
        # while not trade.orderStatus.status == 'Filled':
        #     ib.sleep(1)  # Sleeps to prevent excessive updates, respects API limits
        #     print(f"Current order status: {trade.orderStatus.status}")

        print("Order filled!")

    finally:
        # Disconnect from IB
        # ib.disconnect()
        print('done')

if __name__ == "__main__":
    main()
