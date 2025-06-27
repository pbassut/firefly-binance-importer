from unittest.mock import patch, MagicMock
from datetime import datetime

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from backends.exchanges.impls import binance_wrapper

# Example: Test BinanceConfig initialization
@patch.dict(os.environ, {'BINANCE_API_KEY': 'test_key', 'BINANCE_API_SECRET': 'test_secret'})
def test_binance_config_init():
    config = binance_wrapper.BinanceConfig()
    config.init()
    assert config.api_key == 'test_key'
    assert config.api_secret == 'test_secret'
    assert config.initialized
    assert config.enabled

# Example: Test get_interest_data_from_binance_data
def test_get_interest_data_from_binance_data():
    binance_data = {'interest': '0.5', 'asset': 'BTC', 'time': str(int(datetime.now().timestamp() * 1000))}
    result = binance_wrapper.get_interest_data_from_binance_data(binance_data, 'LENDING', 'DAILY')
    assert result.amount == '0.5'
    assert result.currency == 'BTC'
    assert result.type == 'LENDING'
    assert result.due == 'DAILY'

# Example: Test BinanceClient.connect with mocked Client
@patch('backends.exchanges.impls.binance_wrapper.Client')
def test_binance_client_connect(mock_client):
    mock_instance = MagicMock()
    mock_instance.get_account_status.return_value = {'data': 'Normal'}
    mock_client.return_value = mock_instance
    client = binance_wrapper.BinanceClient()
    assert client.client.get_account_status()['data'] == 'Normal' 
