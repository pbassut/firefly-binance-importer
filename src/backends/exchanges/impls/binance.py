from __future__ import print_function

import os
import sys

from binance.client import Client
from binance.exceptions import BinanceAPIException
from datetime import datetime

from backends.exchanges.exchange_interface import AbstractCryptoExchangeClient, AbstractCryptoExchangeClientModule, \
    ExchangeUnderMaintenanceException
from model.savings import InterestData, InterestDue, SavingsType
from model.transaction import TradeData, TransactionType, TradingPair
from typing import List, Dict
from model.withdrawal_deposit import WithdrawalData, DepositData
from utils import to_ms, from_ms, human_readable_interval, human_readable_interval_ts, interval
import logging


exchange_name = "Binance"

one_day = 24 * 60 * 60

class Config(Dict):
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
class ClientModule(AbstractCryptoExchangeClientModule):

    def is_enabled(self) -> bool:
        config = Config()
        config.init()
        return config.enabled

    def get_exchange_name(self) -> str:
        return exchange_name

    def get_exchange_client(self) -> AbstractCryptoExchangeClient:
        return ClientClass()

    @staticmethod
    def get_instance():
        return ClientModule()


def get_interest_data_from_data(data, type, due) -> InterestData:
    amount = data.get('interest')
    currency = data.get('asset')
    date = datetime.fromtimestamp(int(data.get('time')) / 1000)

    return InterestData(type, amount, currency, date, due)


def get_interests_from_data(interests_data, savings_type, interest_due) -> List[InterestData]:
    result = []
    for interest_data in interests_data:
        inner = get_interest_data_from_data(interest_data, savings_type, interest_due)
        result.append(inner)
    return result


@AbstractCryptoExchangeClient.register
class ClientClass(AbstractCryptoExchangeClient):
    client: Client = None

    config = Config()
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
        self.log.debug("Get trades from " + human_readable_interval_ts(from_timestamp, to_timestamp))
        self.log.debug(self.get_trading_pair_message_log(list_of_trading_pairs))

        list_of_trades: List[TradeData] = []
        for trading_pair in list_of_trading_pairs:
            symbol = trading_pair.security + trading_pair.currency

            try:
                if from_ms(to_timestamp - from_timestamp) - 1 > one_day:
                    trades_total = self.client.get_my_trades(symbol=symbol)
                    relevant_trades = []
                    for trade in trades_total:
                        if int(trade.get('time')) - from_timestamp >= 0:
                            relevant_trades.append(trade)

                    my_trades = relevant_trades
                else:
                    my_trades = self.client.get_my_trades(symbol=symbol, startTime=from_timestamp, endTime=to_timestamp)

                if len(my_trades) > 0:
                    self.log.debug("Found " + str(len(my_trades)) + " trades for " + symbol)
                    list_of_trades.extend(transform_to_trade_data(my_trades, trading_pair))
            except BinanceAPIException as e:
                if e.status_code == 400 and e.code == -1100:
                    self.log.debug("Invalid character found in trading pair: " + trading_pair)
                    self.invalid_trading_pairs.append(trading_pair.security + trading_pair.currency)
                    pass
                elif e.status_code == 400 and e.code == -1121:
                    self.log.debug("Invalid trading pair found: " + trading_pair)
                    self.invalid_trading_pairs.append(trading_pair.security + trading_pair.currency)
                    pass
                else:
                    self.log.error(e)

        return list_of_trades

    def get_savings_interests(self, from_timestamp, to_timestamp) -> List[InterestData]:
        self.log.debug("Get interest from " + human_readable_interval_ts(from_timestamp, to_timestamp))

        result = []

        lending_interest_history_daily = self.client.get_lending_interest_history(lendingType="DAILY", startTime=from_timestamp, endTime=to_timestamp, size=100)
        result.extend(get_interests_from_data(lending_interest_history_daily, SavingsType.LENDING, InterestDue.DAILY))

        lending_interest_history_activity = self.client.get_lending_interest_history(lendingType="ACTIVITY", startTime=from_timestamp, endTime=to_timestamp, size=100)
        result.extend(get_interests_from_data(lending_interest_history_activity, SavingsType.LENDING, InterestDue.ACTIVE))

        lending_interest_history_fixed = self.client.get_lending_interest_history(lendingType="CUSTOMIZED_FIXED", startTime=from_timestamp, endTime=to_timestamp, size=100)
        result.extend(get_interests_from_data(lending_interest_history_fixed, SavingsType.LENDING, InterestDue.FIXED))

        return result

    def get_withdrawals(self, from_timestamp: int, to_timestamp: int) -> List[WithdrawalData]:
        self.log.debug("Get withdrawals from " + human_readable_interval_ts(from_timestamp, to_timestamp))

        all_withdrawal_history = []
        for from_datetime, to_datetime in interval(from_timestamp, to_timestamp):
            self.log.debug("Fetching page of withdrawals: " + human_readable_interval(from_datetime, to_datetime))
            withdrawal_history = self.client.get_withdraw_history(startTime=to_ms(from_datetime.timestamp()),
                                                                  endTime=to_ms(to_datetime.timestamp()),
                                                                  limit=1000)
            all_withdrawal_history.extend(withdrawal_history)

        self.log.debug("Found " + str(len(all_withdrawal_history)) + " withdrawals")

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

    def get_deposits(self, from_timestamp: int, to_timestamp: int) -> List[DepositData]:
        self.log.debug("Get deposits from " + human_readable_interval_ts(from_timestamp, to_timestamp))

        all_deposit_history = []
        for from_date, to_date in interval(from_timestamp, to_timestamp):
            self.log.debug("Fetching page of deposits: " + human_readable_interval(from_date, to_date))
            deposit_history = self.client.get_deposit_history(startTime=to_ms(from_date.timestamp()),
                                                              endTime=to_ms(to_date.timestamp()),
                                                              limit=1000)
            all_deposit_history.extend(deposit_history)

        self.log.debug("Found " + str(len(all_deposit_history)) + " deposits")
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
            self.client = Client(self.config.api_key, self.config.api_secret)
            self.log.debug(self.client.get_account_status())

            if self.client.get_account_status().get('data') != 'Normal':
                self.log.error('Cannot access your account status.')
                sys.exit(1)

            self.log.debug('Account connected.')
        except BinanceAPIException as be:
            if be.code == 1 and be.status_code == 503 and be.message == "System is under maintenance.":
                self.log.error('Binance is under maintenance.', be)
                raise ExchangeUnderMaintenanceException()

            self.log.error('Cannot connect to your account.', be)
            sys.exit(1)

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
