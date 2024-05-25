import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import pytest
from unittest.mock import call, patch, MagicMock, ANY
from bot import IBClient, ZoneRecoveryBot
from alpaca.trading.enums import OrderStatus, OrderSide
from ibapi.contract import Contract
from ibapi.order import Order

mock_data = {
    "Time Series (Daily)": {
        "2021-01-01": {"4. close": "130.00", "5. volume": "1000"},
        "2021-01-02": {"4. close": "135.00", "5. volume": "1050"},
        "2021-01-03": {"4. close": "140.00", "5. volume": "1100"},
    },
    "Time Series (1min)": {
        "2021-01-01 09:30:00": {"4. close": "130.00", "5. volume": "1000"},
        "2021-01-01 09:31:00": {"4. close": "131.00", "5. volume": "1100"},
        "2021-01-01 09:32:00": {"4. close": "132.00", "5. volume": "1200"},
    },
    "top_gainers": [
        {"ticker": "AAPL", "price": "150.00", "change": "+2%"},
        {"ticker": "MSFT", "price": "250.00", "change": "+1.5%"},
    ],
    "top_losers": [
        {"ticker": "TSLA", "price": "600.00", "change": "-1.5%"},
        {"ticker": "AMZN", "price": "3100.00", "change": "-1%"},
    ],
    "most_actively_traded": [
        {"ticker": "GOOGL", "price": "2200.00"},
        {"ticker": "FB", "price": "350.00"},
    ]
}

def matches_expected_call(calls, symbol, qty, limit_price, trade_type='SELL'):
    for call in calls:
        if call[0] == 'submit_order':
            order_details = call[1][0]  # Assuming the order details are the first argument
            # Access attributes directly for custom object
            if (order_details.symbol == symbol and
                order_details.qty == qty and
                order_details.limit_price == limit_price and
                order_details.side == (OrderSide.BUY if trade_type == "BUY" else OrderSide.SELL)):
                return True
    return False

def parse_order_details(order):
    # This function now assumes `order` is an Order object with attributes like qty, price, and action
    return {
        'qty': order.totalQuantity,
        'price': order.lmtPrice,
        'action': order.action  # This should be 'BUY' or 'SELL'
    }

def parse_contract_details(contract):
    # This function assumes `contract` is a Contract object with attributes like symbol
    return {
        'symbol': contract.symbol
    }

def matches_expected_ib_call(calls, symbol, qty, price, trade_type='BUY'):
    for call in calls:
        if len(call.args) > 1 and isinstance(call.args[1], Contract) and isinstance(call.args[2], Order):
            contract_details = parse_contract_details(call.args[1])
            order_details = parse_order_details(call.args[2])
            if (contract_details['symbol'] == symbol and
                order_details['qty'] == qty and
                order_details['price'] == price and
                order_details['action'] == trade_type):
                return True
    return False

@pytest.fixture
def ib_client(mocker):
    # Mock the EClient methods and essential attributes
    mocker.patch('ibapi.client.EClient.__init__', return_value=None)
    mocker.patch('ibapi.client.EClient.run', return_value=None) 
    connect_mock = mocker.patch('ibapi.client.EClient.connect')
    disconnect_mock = mocker.patch('ibapi.client.EClient.disconnect')
    is_connected_mock = mocker.patch('ibapi.client.EClient.isConnected', return_value=True)
    
    # Simulate msg_queue and conn initialization if it's used directly
    client = IBClient(client_id=1)
    client.msg_queue = MagicMock()
    client.conn = MagicMock()
    client.order_status = MagicMock(return_value='Filled')
    client.nextValidOrderId = 100  # Starting order ID

    # Mock reqIds to simulate order ID fetching and incrementation
    def increment_order_id(dummy):
        client.nextValidOrderId += 1  # Increment order ID on each call
        return client.nextValidOrderId

    req_ids_mock = mocker.patch.object(client, 'reqIds')
    req_ids_mock.side_effect = increment_order_id
    place_order_mock = mocker.patch.object(client, 'placeOrder')

    client.connect_mock = connect_mock
    client.disconnect_mock = disconnect_mock
    client.is_connected_mock = is_connected_mock
    client.req_ids_mock = req_ids_mock
    client.place_order_mock = place_order_mock

    return client

def test_stop(ib_client):
    # Test the stop method to ensure it properly calls disconnect
    ib_client.stop()
    ib_client.disconnect_mock.assert_called_once()

class MockOrder:
    status=OrderStatus.FILLED
    filled_avg_price=None
    filled_qty=1

@pytest.fixture
def mock_alpaca_client():
    submit_order_mock = MagicMock()
    get_order_mock = MagicMock()
    return MagicMock(submit_order=submit_order_mock, get_order=get_order_mock)

@pytest.fixture
def zone_recovery_bot(ib_client, mock_alpaca_client, mocker):
    mocker.patch('requests.get', return_value=MagicMock(
        json=MagicMock(return_value=mock_data),
        raise_for_status=MagicMock()
    ))
    bot = ZoneRecoveryBot(['AAPL', 'GOOGL'], ib_client, mock_alpaca_client)
    bot.logic.rsi_period = 3

    return bot

def test_start(zone_recovery_bot):
    # This Test starts and checks if we have enough inital data, If we don't we just keep 
    # fetching until we eventually have enough records to use it for our rsi
    zone_recovery_bot.running = MagicMock()
    zone_recovery_bot.running.__bool__.side_effect = [True, False]
    with patch('time.sleep', return_value=None) as mock_sleep:
        zone_recovery_bot.start()
        assert mock_sleep.mock_calls == [call(60)]
        assert zone_recovery_bot.stocks_to_check == {
            'AAPL': {
                'fetched': True,
                'prices': [135.0, 140.0, 132.0],
                'volumes': [1050, 1100, 1200],
                'long': [], 'short': [],
                'timestamps': ['2021-01-02', '2021-01-03', '2021-01-01 09:32:00'],
                'previous_rsi': 29.411764705882362
            }, 
            'GOOGL': {
                'fetched': True,
                'prices': [135.0, 140.0, 132.0],
                'volumes': [1050, 1100, 1200],
                'long': [], 'short': [],
                'timestamps': ['2021-01-02', '2021-01-03', '2021-01-01 09:32:00'],
                'previous_rsi': 29.411764705882362
            }
        }

def generate_trend_data():
    # Generate data for 14 trading days
    aapl_prices = [100 + i * 2 for i in range(14)]  # Gradual increase
    googl_prices = [200 - i * 2 for i in range(14)]  # Gradual decrease
    dates = [f"2021-01-{i:02d}" for i in range(1, 15)]

    aapl_data = {date: {"4. close": str(price), "5. volume": "1000"} for date, price in zip(dates, aapl_prices)}
    googl_data = {date: {"4. close": str(price), "5. volume": "1000"} for date, price in zip(dates, googl_prices)}

    return {
        "AAPL": aapl_data,
        "GOOGL": googl_data
    }

def generate_latest_data(index):
    return {
        "Time Series (1min)": {
           f"2021-01-15 09:{index:02}:00": {"4. close": f"1{30 + index}.00", "5. volume": "1000"}
            }
        }

@pytest.fixture
def zone_recovery_bot_sophisticated_trades(ib_client, mock_alpaca_client, mocker):
    aapl_index = googl_index = 0
    def mock_api_response(*args, **kwargs):
        nonlocal aapl_index, googl_index
        if 'function' in kwargs['params']:
            if kwargs['params']['function'] == 'TOP_GAINERS_LOSERS':
                response = mock_data
            elif kwargs['params']['function'] == 'TIME_SERIES_DAILY':
                response = {"Time Series (Daily)": generate_trend_data()[kwargs['params']['symbol']]}
            elif kwargs['params']['function'] == 'TIME_SERIES_INTRADAY':
                symbol = kwargs['params']['symbol']
                if symbol == 'AAPL':
                    response = generate_latest_data(aapl_index)
                    aapl_index += 1
                else:
                    response = generate_latest_data(googl_index)
                    googl_index += 1
        return MagicMock(json=MagicMock(return_value=response), raise_for_status=MagicMock())

    mocker.patch('requests.get', lambda url, params: mock_api_response(url, params=params))


    return ZoneRecoveryBot(['AAPL', 'GOOGL'], ib_client, mock_alpaca_client)

inital_fetch_expected_data = {'AAPL': {'fetched': True, 'prices': [102.0, 104.0, 106.0, 108.0, 110.0, 112.0, 114.0, 116.0, 118.0, 120.0, 122.0, 124.0, 126.0, 130.0], 'volumes': [1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000], 'long': [], 'short': [], 'timestamps': ['2021-01-02', '2021-01-03', '2021-01-04', '2021-01-05', '2021-01-06', '2021-01-07', '2021-01-08', '2021-01-09', '2021-01-10', '2021-01-11', '2021-01-12', '2021-01-13', '2021-01-14', '2021-01-15 09:00:00'], 'previous_rsi': 100.0}, 'GOOGL': {'fetched': True, 'prices': [198.0, 196.0, 194.0, 192.0, 190.0, 188.0, 186.0, 184.0, 182.0, 180.0, 178.0, 176.0, 174.0, 130.0], 'volumes': [1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000], 'long': [], 'short': [], 'timestamps': ['2021-01-02', '2021-01-03', '2021-01-04', '2021-01-05', '2021-01-06', '2021-01-07', '2021-01-08', '2021-01-09', '2021-01-10', '2021-01-11', '2021-01-12', '2021-01-13', '2021-01-14', '2021-01-15 09:00:00'], 'previous_rsi': 0.0}}
def test_trading_decisions(zone_recovery_bot_sophisticated_trades):
    zone_recovery_bot_sophisticated_trades.ib_client.order_statuses = {}
    run_idx = 0
    def run_checker():
        nonlocal run_idx
        avg_fill_price = 130 + run_idx
        zone_recovery_bot_sophisticated_trades.ib_client.order_statuses[100 + run_idx + 1] = {
                "status": 'Filled',
                "filled": 1,
                "avgFillPrice": avg_fill_price
            }
        mock_order = MockOrder()
        mock_order.filled_avg_price = avg_fill_price
        zone_recovery_bot_sophisticated_trades.alpaca_trading_client.get_order.return_value = mock_order
        zone_recovery_bot_sophisticated_trades.ib_client.orders_filled.set()
        if run_idx >= 10:
            return False
        if run_idx == 1:
            # After one check we should see that we found condition for an overbought AAPL and an oversold GOOGL
            # which gives us inital data and a long and short trade
            assert zone_recovery_bot_sophisticated_trades.stocks_to_check == inital_fetch_expected_data
        if run_idx == 2:
            # After two iterations, we will have established our entry point and made two trades, Apple detected a overbought opportunity but the stock kept on rising
            # hence a short position was opnened to hedge against it.
            assert zone_recovery_bot_sophisticated_trades.stocks_to_check['AAPL']['short'] ==  []
            assert zone_recovery_bot_sophisticated_trades.stocks_to_check['AAPL']['long'] ==  []
            # Apple detected a oversold opportunity and corectly opened two long postions as the RSI indicated this trend.
            assert zone_recovery_bot_sophisticated_trades.stocks_to_check['GOOGL']['short'] == []
            assert zone_recovery_bot_sophisticated_trades.stocks_to_check['GOOGL']['long'] == [{'price': 131, 'qty': 1}]
        if run_idx == 7:
            # The bot reached the maximum trades for this stock and closed the positions
            assert zone_recovery_bot_sophisticated_trades.stocks_to_check['GOOGL']['short'] == []
            assert zone_recovery_bot_sophisticated_trades.stocks_to_check['GOOGL']['long'] == []
            assert zone_recovery_bot_sophisticated_trades.stocks_to_check['AAPL']['short'] == []
            assert zone_recovery_bot_sophisticated_trades.stocks_to_check['AAPL']['long'] == []
            # check that we took sold the long positions
            mock_calls = zone_recovery_bot_sophisticated_trades.alpaca_trading_client.mock_calls
            assert matches_expected_call(mock_calls, 'GOOGL', 5.0, 136.0)
            # check that we also cleared out the short position that we took out on the ib client
            assert zone_recovery_bot_sophisticated_trades.total_session_profit == 2.2556390977443606
        run_idx += 1
        return True
    

    # Run the bot and simulate trading decisions
    zone_recovery_bot_sophisticated_trades.running = MagicMock()
    zone_recovery_bot_sophisticated_trades.running.__bool__.side_effect = run_checker
    with patch('time.sleep', return_value=None):
        zone_recovery_bot_sophisticated_trades.start()
