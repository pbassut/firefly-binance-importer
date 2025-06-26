from __future__ import print_function

import os

from binance.client import Client
from binance.exceptions import BinanceAPIException
from datetime import datetime

from backends.exchanges.exchange_interface import AbstractCryptoExchangeClient, AbstractCryptoExchangeClientModule, \
    ExchangeUnderMaintenanceException
from model.savings import InterestData, InterestDue, SavingsType
from model.transaction import TradeData, TransactionType, TradingPair
from typing import List, Dict
from model.withdrawal_deposit import WithdrawalData, DepositData

import logging

exchange_name = "Binance"


def human_readable_interval(from_timestamp, to_timestamp):
    return str(datetime.fromtimestamp(from_timestamp / 1000)) + " to " + str(datetime.fromtimestamp(to_timestamp / 1000 - 1))

def to_ms(timestamp):
    return int(timestamp * 1000)

def from_ms(timestamp):
    return int(timestamp / 1000)

twentyfour_hours = 24 * 60 * 60

def ninety_days_ms(timestamp):
    return timestamp + 90 * twentyfour_hours * 1000

class BinanceConfig(Dict):
    failed = False
    enabled = False
    initialized = False
    api_key = None
    api_secret = None

    def init(self):
        try:
            self.api_key =  os.environ['BINANCE_API_KEY']
            self.api_secret = os.environ['BINANCE_API_SECRET']
            self.initialized = True
            self.enabled = True
        except Exception as e:
            self.failed = True


@AbstractCryptoExchangeClientModule.register
class BinanceClientModule(AbstractCryptoExchangeClientModule):

    def is_enabled(self) -> bool:
        config = BinanceConfig()
        config.init()
        return config.enabled

    def get_exchange_name(self) -> str:
        return exchange_name

    def get_exchange_client(self) -> AbstractCryptoExchangeClient:
        return BinanceClient()

    @staticmethod
    def get_instance():
        return BinanceClientModule()


def get_interest_data_from_binance_data(binance_data, type, due) -> InterestData:
    amount = binance_data.get('interest')
    currency = binance_data.get('asset')
    date = datetime.fromtimestamp(int(binance_data.get('time')) / 1000)

    return InterestData(type, amount, currency, date, due)


def get_interests_from_binance_data(interests_binance_data, savings_type, interest_due) -> List[InterestData]:
    result = []
    for interest_binance_data in interests_binance_data:
        inner = get_interest_data_from_binance_data(interest_binance_data, savings_type, interest_due)
        result.append(inner)
    return result


@AbstractCryptoExchangeClient.register
class BinanceClient(AbstractCryptoExchangeClient):
    client = None

    config = BinanceConfig()
    config.init()

    def __init__(self):
        self.log = logging.getLogger("[BINANCE]")
        self.connect()

    def get_trading_pairs(self, list_of_symbols_and_codes: List[str]) -> List[TradingPair]:
        binance_products = self.client.get_products().get('data')
        potential_trading_pairs = []

        for symbol_or_code in list_of_symbols_and_codes:
            for traded_symbol_or_code in list_of_symbols_and_codes:
                if symbol_or_code == traded_symbol_or_code:
                    continue

                new_trading_pair = TradingPair(symbol_or_code, traded_symbol_or_code)
                potential_trading_pairs.append(new_trading_pair)

        result = []
        for product in binance_products:
            for potential_trading_pair in potential_trading_pairs:
                if product.get('st') != 'TRADING':
                    continue

                if product.get('b') == potential_trading_pair.security and product.get('q') == potential_trading_pair.currency:
                    result.append(potential_trading_pair)

        unique_trading_pairs = set(dict.fromkeys(potential_trading_pairs)) - set(dict.fromkeys(result))
        self.log.debug('discarding potential_trading_pairs: ' + str(list(map(lambda x: x.security + x.currency, unique_trading_pairs))))
        return result

    def get_trades(self, from_timestamp, to_timestamp, list_of_trading_pairs) -> List[TradeData]:
        list_of_trades: List[TradeData] = []

        self.log.debug("Get trades from " + human_readable_interval(from_timestamp, to_timestamp))
        self.log.debug(self.get_trading_pair_message_log(list_of_trading_pairs))

        for trading_pair in list_of_trading_pairs:
            symbol = trading_pair.security + trading_pair.currency

            try:
                if from_ms(to_timestamp - from_timestamp) - 1 > twentyfour_hours:
                    trades_total = self.client.get_my_trades(symbol=symbol)
                    relevant_trades = []
                    for trade in trades_total:
                        if int(trade.get('time')) - from_timestamp >= 0:
                            relevant_trades.append(trade)
                    my_trades = relevant_trades
                else:
                    my_trades = self.client.get_my_trades(symbol=symbol, startTime=from_timestamp, endTime=to_timestamp)

                if len(my_trades) > 0:
                    list_of_trades.extend(transform_to_trade_data(my_trades, trading_pair))
                    self.log.debug(my_trades)
                    self.log.debug("Found " + str(len(my_trades)) + " trades for " + symbol)
            except BinanceAPIException as e:
                if e.status_code == 400 and e.code == -1100:
                    # logger.debug("Invalid character found in trading pair: " + trading_pair)
                    # self.invalid_trading_pairs.append(trading_pair.security + trading_pair.currency)
                    pass
                elif e.status_code == 400 and e.code == -1121:
                    # logger.debug("Invalid trading pair found: " + trading_pair)
                    # self.invalid_trading_pairs.append(trading_pair.security + trading_pair.currency)
                    pass
                else:
                    self.log.error(e)

        return list_of_trades

    def get_savings_interests(self, from_timestamp, to_timestamp, list_of_assets) -> List[InterestData]:
        self.log.debug("Get interest from " + human_readable_interval(from_timestamp, to_timestamp))

        result = []
        lending_interest_history_daily = self.client.get_lending_interest_history(lendingType="DAILY", startTime=from_timestamp, endTime=to_timestamp, size=100)

        result.extend(get_interests_from_binance_data(lending_interest_history_daily, SavingsType.LENDING, InterestDue.DAILY))
        lending_interest_history_activity = self.client.get_lending_interest_history(lendingType="ACTIVITY", startTime=from_timestamp, endTime=to_timestamp, size=100)
        result.extend(get_interests_from_binance_data(lending_interest_history_activity, SavingsType.LENDING, InterestDue.ACTIVE))

        lending_interest_history_fixed = self.client.get_lending_interest_history(lendingType="CUSTOMIZED_FIXED", startTime=from_timestamp, endTime=to_timestamp, size=100)
        result.extend(get_interests_from_binance_data(lending_interest_history_fixed, SavingsType.LENDING, InterestDue.FIXED))

        return result

    def get_withdrawals(self, from_timestamp: int, to_timestamp: int, list_of_assets: List[str]) -> List[WithdrawalData]:
        self.log.debug("Get withdrawals from " + human_readable_interval(from_timestamp, to_timestamp))

        from_datetime = datetime.fromtimestamp(from_ms(from_timestamp))
        to_datetime = datetime.fromtimestamp(from_ms(from_timestamp) + 90 * twentyfour_hours)

        all_withdrawal_history = []
        while not to_ms(from_datetime.timestamp()) >= to_timestamp:
            withdrawal_history = self.client.get_withdraw_history(startTime=to_ms(from_datetime.timestamp()),
                                                                  endTime=to_ms(to_datetime.timestamp()))
            all_withdrawal_history.extend(withdrawal_history)

            from_datetime = datetime.fromtimestamp(to_datetime.timestamp() + 1)
            ninety_days_ahead = ninety_days_ms(to_datetime.timestamp())
            to_datetime = datetime.fromtimestamp(ninety_days_ahead if ninety_days_ahead < to_timestamp else to_timestamp)

        return [
            WithdrawalData(
                trading_platform=exchange_name,
                amount=binance_withdrawal.get("amount"),
                asset=binance_withdrawal.get("asset"),
                timestamp=binance_withdrawal.get("applyTime"),
                target_address=binance_withdrawal.get("address"),
                transaction_fee=binance_withdrawal.get("transactionFee"),
                transaction_id=binance_withdrawal.get("txId")
            ) for binance_withdrawal in all_withdrawal_history
        ]

    def get_deposits(self, from_timestamp: int, to_timestamp: int, list_of_assets: List[str]) -> List[DepositData]:
        self.log.debug("Get deposits from " + human_readable_interval(from_timestamp, to_timestamp))

        from_datetime = datetime.fromtimestamp(from_ms(from_timestamp))
        to_datetime = datetime.fromtimestamp(from_ms(from_timestamp) + 90 * twentyfour_hours)

        all_deposit_history = []
        while not to_ms(from_datetime.timestamp()) >= to_timestamp:
            deposit_history = self.client.get_deposit_history(startTime=to_ms(from_datetime.timestamp()),
                                                              endTime=to_ms(to_datetime.timestamp()))
            all_deposit_history.extend(deposit_history)
            from_datetime = datetime.fromtimestamp(to_datetime.timestamp() + 1)
            to_datetime = datetime.fromtimestamp(ninety_days_ms(to_datetime.timestamp())) \
                if to_datetime.timestamp() < to_timestamp else to_timestamp

        return [
            DepositData(
                trading_platform=exchange_name,
                amount=binance_deposit.get("amount"),
                asset=binance_deposit.get("asset"),
                timestamp=binance_deposit.get("insertTime"),
                target_address=binance_deposit.get("address"),
                transaction_id=binance_deposit.get("txId")
            ) for binance_deposit in all_deposit_history
        ]

    def connect(self):
        try:
            self.log.debug('Trying to connect to your account...')
            new_client = Client(self.config.api_key, self.config.api_secret)
            self.log.debug(new_client.get_account_status())
            if new_client.get_account_status().get('data') != 'Normal':
                raise Exception("Binance: Cannot access your account status.")
            self.log.debug('Connection to your account established.')
            self.client = new_client
        except BinanceAPIException as be:
            if be.code == 1 and be.status_code == 503 and be.message == "System is under maintenance.":
                raise ExchangeUnderMaintenanceException()
            else:
                self.log.error('Cannot connect to your account.', be)
                raise Exception('Cannot connect to your account.', be)
        except Exception as e:
            self.log.error('Cannot connect to your account.', e)
            raise Exception('Cannot connect to your account.', e)

    @staticmethod
    def get_trading_pair_message_log(list_of_trading_pairs):
        log_message = "Trading pairs: [" 
        trading_pair_counter = 0
        for trading_pair in list_of_trading_pairs:
            if trading_pair_counter > 0:
                log_message += ","
            log_message += " \"" + trading_pair.security + trading_pair.currency + "\" "
            trading_pair_counter += 1
        log_message += "]"
        return log_message


def transform_buy_trade(buy, trading_pair) -> TradeData:
    commission_amount = buy.get('commission')
    commission_asset = buy.get('commissionAsset')
    currency_amount = buy.get('qty')
    security_amount = buy.get('quoteQty')
    trade_id = buy.get('id')
    trade_time = buy.get('time')
    trading_platform = exchange_name
    result = TradeData(trading_platform, commission_amount, commission_asset, currency_amount, security_amount,
                           trading_pair, TransactionType.BUY, trade_id, trade_time)
    return result


def transform_sell_trade(sell, trading_pair) -> TradeData:
    commission_amount = sell.get('commission')
    commission_asset = sell.get('commissionAsset')
    currency_amount = sell.get('quoteQty')
    security_amount = sell.get('qty')
    trade_id = sell.get('id')
    trade_time = sell.get('time')
    trading_platform = exchange_name
    return TradeData(trading_platform, commission_amount, commission_asset, currency_amount, security_amount,
                           trading_pair, TransactionType.SELL, trade_id, trade_time)


def transform_to_trade_data(my_trades, trading_pair) -> List[TradeData]:
    result = []

    for trade in my_trades:
        if trade.get('isBuyer'):
            result.append(transform_buy_trade(trade, trading_pair))
        else:
            result.append(transform_sell_trade(trade, trading_pair))

    return result
