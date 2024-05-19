import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import sys
import os
import pytest
from unittest.mock import MagicMock, patch
import alpaca_trade_api as tradeapi
from bot import IBClient, ZoneRecoveryBot

@pytest.fixture
def mock_ib_client():
    client = MagicMock(spec=IBClient)
    client.nextValidOrderId = 1
    return client

@pytest.fixture
def mock_alpaca_client():
    client = MagicMock(spec=tradeapi.REST)
    return client

@pytest.fixture
def setup_zone_recovery_bot(mock_ib_client, mock_alpaca_client):
    with patch('threading.Thread') as mock_thread, \
         patch('get_market_data.GetMarketData.get_potential_candidates') as mock_get_potential_candidates, \
         patch('get_market_data.GetMarketData.fetch_initial_data') as mock_fetch_initial_data, \
         patch('get_market_data.GetMarketData.fetch_latest_price') as mock_fetch_latest_price, \
         patch('time.sleep', return_value=None):

        # Mock threading
        mock_thread.return_value.start = MagicMock()
        
        # Mock market data service methods
        mock_get_potential_candidates.return_value = [("TEST", "extra_value")]
        mock_fetch_initial_data.return_value = ([(100, "2023-05-01")], [1000])
        mock_fetch_latest_price.return_value = (100, "2023-05-01")

        tickers = ["TEST"]
        bot = ZoneRecoveryBot(tickers, mock_ib_client, mock_alpaca_client)
        
        # Override the running attribute to control the loop
        bot.running = False
        
        yield bot
        bot.stop()

def test_market_going_up(setup_zone_recovery_bot):
    mock_market_data = [
        (100, "2023-05-01"), (105, "2023-05-02"), (110, "2023-05-03"),
        (115, "2023-05-04"), (120, "2023-05-05")
    ]
    setup_zone_recovery_bot.market_data_service.fetch_initial_data = MagicMock(return_value=(mock_market_data, []))
    setup_zone_recovery_bot.market_data_service.fetch_latest_price = MagicMock(side_effect=mock_market_data)
    setup_zone_recovery_bot.save_metadata = MagicMock()  # Mock save_metadata to avoid file I/O

    # with patch.object(setup_zone_recovery_bot, 'running', side_effect=[True, False]):
    #     setup_zone_recovery_bot.fetch_data_periodically()

    # assert setup_zone_recovery_bot.logic.update_price.call_count == len(mock_market_data)




# def test_market_going_down(setup_zone_recovery_bot):
#     mock_market_data = [
#         (120, "2023-05-01"), (115, "2023-05-02"), (110, "2023-05-03"),
#         (105, "2023-05-04"), (100, "2023-05-05")
#     ]
#     setup_zone_recovery_bot.market_data_service.fetch_initial_data = MagicMock(return_value=(mock_market_data, []))
#     setup_zone_recovery_bot.market_data_service.fetch_latest_price = MagicMock(side_effect=mock_market_data)
#     setup_zone_recovery_bot.save_metadata = MagicMock()  # Mock save_metadata to avoid file I/O

#     with patch('threading.Thread.start'):
#         with patch.object(setup_zone_recovery_bot, 'fetch_data_periodically', side_effect=lambda: None):
#             setup_zone_recovery_bot.start()

#     setup_zone_recovery_bot.fetch_data()

#     assert setup_zone_recovery_bot.logic.update_price.call_count == len(mock_market_data)

# def test_market_going_sideways(setup_zone_recovery_bot):
#     mock_market_data = [
#         (100, "2023-05-01"), (101, "2023-05-02"), (100, "2023-05-03"),
#         (101, "2023-05-04"), (100, "2023-05-05")
#     ]
#     setup_zone_recovery_bot.market_data_service.fetch_initial_data = MagicMock(return_value=(mock_market_data, []))
#     setup_zone_recovery_bot.market_data_service.fetch_latest_price = MagicMock(side_effect=mock_market_data)
#     setup_zone_recovery_bot.save_metadata = MagicMock()  # Mock save_metadata to avoid file I/O

#     with patch('threading.Thread.start'):
#         with patch.object(setup_zone_recovery_bot, 'fetch_data_periodically', side_effect=lambda: None):
#             setup_zone_recovery_bot.start()

#     setup_zone_recovery_bot.fetch_data()

#     assert setup_zone_recovery_bot.logic.update_price.call_count == len(mock_market_data)


