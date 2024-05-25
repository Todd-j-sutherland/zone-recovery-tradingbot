import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import pytest
from zone_recovery_logic import ZoneRecoveryLogic
from utils import calculate_rsi

stocks_data = {
    "DUO": {"prices": [1.68, 0.3988, 2.0, 2.1, 2.2], "last_action": None, "entry_price": None}
}

@pytest.fixture
def setup_zone_recovery_logic():
    logic = ZoneRecoveryLogic(rsi_period=5, entry_rsi_low=30, entry_rsi_high=70)
    return logic

def test_calculate_rsi_basic(setup_zone_recovery_logic):
    prices = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    expected_rsi = 100  # This is a simple increasing series; RSI should be at its max
    rsi = calculate_rsi(prices, setup_zone_recovery_logic.rsi_period)
    assert rsi == expected_rsi

def test_calculate_rsi_edge_case_zero_down(setup_zone_recovery_logic):
    prices = [5, 5, 5, 5, 5, 5, 5, 5, 5, 5]
    expected_rsi = 100  # No changes in price; should be at its max because no losses
    rsi = calculate_rsi(prices, setup_zone_recovery_logic.rsi_period)
    assert rsi == expected_rsi

def test_calculate_rsi_mixed_prices(setup_zone_recovery_logic):
    prices = [1, 2, 3, 2, 1, 2, 3, 4, 3, 2]
    expected_rsi = 44.79  # Corrected value based on actual RSI calculation
    rsi = calculate_rsi(prices, setup_zone_recovery_logic.rsi_period)
    assert round(rsi, 2) == expected_rsi  # Allow small rounding differences

def test_calculate_rsi_with_real_data(setup_zone_recovery_logic):
    prices = [45.15, 46.26, 46.5, 46.23, 46.5, 46.51, 46.52, 46.4, 46.36, 46.52]
    expected_rsi = 73.35  # Corrected value based on actual RSI calculation
    rsi = calculate_rsi(prices, setup_zone_recovery_logic.rsi_period)
    assert round(rsi, 2) == expected_rsi  # Allow small rounding differences

def test_calculate_percentage_profit(setup_zone_recovery_logic):
    long = [{"price": 1.0, "qty": 10}, {"price": 2.0, "qty": 5}]
    short = [{"price": 3.0, "qty": 5}]

    current_price = 4.0
    total_profit = setup_zone_recovery_logic.calculate_percentage_profit(long, short, current_price)
    assert total_profit == 100.0

def test_calculate_rsi_and_check_profit_closes_all(setup_zone_recovery_logic):
    stock_data = {
            "long": [{"price": 1.0, "qty": 10}],
            "short": [{"price": 3.0, "qty": 5}],
            "prices": [1, 1, 1, 1, 1]
    }

    result = setup_zone_recovery_logic.calculate_rsi_and_check_profit(stock_data, "DUO", 4.0)
    assert result == ('CLOSE_ALL', 4.0, 100.0)
    assert stock_data == {"long": [{"price": 1.0, "qty": 10}], "short": [{"price": 3.0, "qty": 5}], "prices": [1, 1, 1, 1, 1], 'previous_rsi': 100.0}

def test_calculate_rsi_decending_trend_do_not_open_position(setup_zone_recovery_logic):
    stock_data = {
            "long": [],
            "short": [],
            "prices": [10, 9, 8, 7, 6, 5, 4, 3, 2, 1]
    }
    
    result = setup_zone_recovery_logic.calculate_rsi_and_check_profit(stock_data, "DUO", 1.0)
    
    assert result == None

def test_calculate_rsi_ascending_trend_and_do_not_open_position(setup_zone_recovery_logic):
    stock_data = {
            "long": [],
            "short": [],
            "prices": [1, 2, 3, 4, 5, 6, 7, 8, 9]
    }
    result = setup_zone_recovery_logic.calculate_rsi_and_check_profit(stock_data, "DUO", 10.0)
    assert result == None

