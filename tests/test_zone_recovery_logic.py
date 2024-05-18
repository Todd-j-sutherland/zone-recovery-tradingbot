import sys
import os
import logging
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
import numpy as np
from zone_recovery_logic import ZoneRecoveryLogic

@pytest.fixture
def stocks_data():
    return {
        'AAPL': {'prices': [], 'entry_price': None},
        'GOOGL': {'prices': [], 'entry_price': None}
    }

@pytest.fixture
def zone_recovery(stocks_data):
    return ZoneRecoveryLogic(stocks_data)

def test_initialization(zone_recovery, stocks_data):
    assert zone_recovery.stocks_data == stocks_data
    assert zone_recovery.rsi_period == 14
    assert zone_recovery.entry_rsi_low == 30
    assert zone_recovery.entry_rsi_high == 70
    assert zone_recovery.profit_target == 0.05
    assert all(stock in zone_recovery.positions for stock in stocks_data)
    assert all(zone_recovery.positions[stock] == {'quantity': 0, 'avg_price': 0} for stock in stocks_data)

def test_update_price(zone_recovery):
    prices = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]
    for price in prices:
        signal = zone_recovery.update_price('AAPL', price)
        if len(zone_recovery.stocks_data['AAPL']['prices']) < zone_recovery.rsi_period:
            assert signal is None
        elif len(zone_recovery.stocks_data['AAPL']['prices']) == zone_recovery.rsi_period:
            assert isinstance(signal, tuple) and len(signal) == 2

def test_rsi_calculation_and_signal(zone_recovery):
    prices = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14]
    for price in prices:
        zone_recovery.update_price('AAPL', price)
    signal = zone_recovery.update_price('AAPL', 15)
    assert signal is not None
    assert signal[0] == 'SELL' or signal[0] == 'BUY'

def test_on_order_response(zone_recovery):
    order_response = {
        'contract': {'symbol': 'AAPL'},
        'order': {'action': 'BUY'},
        'filled': 10,
        'avgFillPrice': 150
    }
    zone_recovery.on_order_response('order1', order_response)
    assert zone_recovery.positions['AAPL']['quantity'] == 10
    assert zone_recovery.positions['AAPL']['avg_price'] == 150

    order_response_sell = {
        'contract': {'symbol': 'AAPL'},
        'order': {'action': 'SELL'},
        'filled': 5,
        'avgFillPrice': 160
    }
    zone_recovery.on_order_response('order2', order_response_sell)
    assert zone_recovery.positions['AAPL']['quantity'] == 5


def test_profit_target(zone_recovery, caplog):
    # Simulate a scenario where 'AAPL' is bought and then reaches a profit target
    with caplog.at_level(logging.INFO):
        # Initialize the prices leading up to the trigger
        prices = [150, 155, 160, 165, 170, 175, 180, 185, 190, 195, 200, 205, 210, 215, 220]
        for price in prices:
            zone_recovery.update_price('AAPL', price)
        
        # Assume a BUY was triggered at 220
        zone_recovery.stocks_data['AAPL']['last_action'] = 'BUY'
        zone_recovery.stocks_data['AAPL']['entry_price'] = 220

        # Update price to simulate reaching the profit target
        profit_price = 220 * (1 + zone_recovery.profit_target)  # 5% profit target
        action, achieved_price = zone_recovery.update_price('AAPL', profit_price)

        # Verify that the SELL action is triggered at the profit price
        assert action == 'SELL'
        assert achieved_price == profit_price

        # Check if logs correctly report the profit taking
        profit_logging = any("Profit target reached" in record.message for record in caplog.records)
        assert profit_logging

        # Reset for SELL scenario
        caplog.clear()
        zone_recovery.stocks_data['AAPL']['last_action'] = 'SELL'
        zone_recovery.stocks_data['AAPL']['entry_price'] = 220

        # Update price to simulate reaching the profit target for a SELL
        loss_price = 220 * (1 - zone_recovery.profit_target)  # 5% profit target
        action, achieved_price = zone_recovery.update_price('AAPL', loss_price)

        # Verify that the BUY action is triggered at the loss price
        assert action == 'BUY'
        assert achieved_price == loss_price

        # Check if logs correctly report the stop loss action
        loss_logging = any("Profit target reached" in record.message for record in caplog.records)
        assert loss_logging

def test_random_trading_sequence(zone_recovery):
    np.random.seed(42)  # for reproducible results
    initial_price = 100  # starting price
    prices = [initial_price]
    fluctuations = np.random.normal(0, 2, 100)  # generate 100 price changes

    for change in fluctuations:
        new_price = prices[-1] + change
        prices.append(new_price)

    last_action = None
    entry_price = None

    for price in prices:
        signal = zone_recovery.update_price('AAPL', price)

        if signal:
            action, action_price = signal
            print(f"Received {action} signal at price {action_price}, last action was {last_action}")

            if last_action == 'BUY':
                if action == 'SELL':
                    # Check if the profit target for a sell has been reached
                    assert action_price >= entry_price * (1 + zone_recovery.profit_target)
                else:
                    # If a BUY signal is received again, check if it's due to a valid RSI condition
                    # This condition should be explicitly verified, perhaps by checking RSI directly if exposed by ZoneRecoveryLogic
                    pass
            elif last_action == 'SELL':
                if action == 'BUY':
                    # Check if the profit target for a buy has been reached
                    assert action_price <= entry_price * (1 - zone_recovery.profit_target)
                else:
                    # If a SELL signal is received again, check if it's due to a valid RSI condition
                    # This condition should also be explicitly verified
                    pass

            # Update the last action and entry price
            last_action = action
            entry_price = action_price
