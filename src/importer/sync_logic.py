import config as config
import backends.firefly.firefly_wrapper as firefly_wrapper
from model.transaction import TradeData, TransactionType
from backends.exchanges import exchange_interface_factory
from backends.firefly.firefly_wrapper import TransactionCollection
from typing import List
import re
from backends.public_ledgers import available_explorer
import logging
from datetime import datetime
from utils import from_ms
from enum import Enum

class IntervalEnum(Enum):
    HOURLY = "hourly"
    DAILY = "daily"
    DEBUG = "debug"

class SyncLogic:
    def __init__(self, trading_platform):
        self.trading_platform = trading_platform
        self.log = logging.getLogger("[" + trading_platform.upper() + "] [SYNC_LOGIC]")
        self.firefly = firefly_wrapper.FireflyWrapper(trading_platform)

    def get_transaction_collections_from_trade_data(self, list_of_trades: List[TradeData]):
        return list(map(lambda trade: TransactionCollection(trade, None, None, None, None), list_of_trades))

    def augment_transaction_collection_with_firefly_accounts(self, transaction_collection, firefly_account_collection):
        if transaction_collection.trade_data.type is TransactionType.BUY:
            if firefly_account_collection.security == transaction_collection.trade_data.trading_pair.security:
                transaction_collection.to_ff_account = firefly_account_collection.asset_account.attributes
            if firefly_account_collection.security == transaction_collection.trade_data.trading_pair.currency:
                transaction_collection.from_ff_account = firefly_account_collection.asset_account.attributes

        elif transaction_collection.trade_data.type is TransactionType.SELL:
            if firefly_account_collection.security == transaction_collection.trade_data.trading_pair.currency:
                transaction_collection.to_ff_account = firefly_account_collection.asset_account.attributes
            if firefly_account_collection.security == transaction_collection.trade_data.trading_pair.security:
                transaction_collection.from_ff_account = firefly_account_collection.asset_account.attributes

        else:
            pass

        commission_asset = transaction_collection.trade_data.commission_asset
        if firefly_account_collection.security == commission_asset:
            transaction_collection.commission_account = firefly_account_collection.expense_account.attributes

        if commission_asset in firefly_account_collection.asset_account.attributes.currency_symbol \
                or commission_asset in firefly_account_collection.asset_account.attributes.currency_code:
            transaction_collection.from_commission_account = firefly_account_collection.asset_account.attributes

    def log_initial_message(self, from_timestamp, to_timestamp, init, component):
        from_date = datetime.fromtimestamp(from_ms(from_timestamp))
        to_date = datetime.fromtimestamp(from_ms(to_timestamp))
        message = "Importing " + ("all historical " if init else "") + component + " from " + str(from_date) + " to " + str(to_date)
        if not init:
            epochs_to_calculate = self.get_epochs_differences(from_timestamp, to_timestamp, config.sync_inverval)
            message += ", " + str(epochs_to_calculate) + " intervals."

        self.log.debug(message)

    def handle_deposits(self, from_timestamp, to_timestamp, init, exchange_interface,
                        firefly_account_collections):
        self.log_initial_message(from_timestamp, to_timestamp, init, "deposits")

        self.log.debug("1. Get deposits from exchange")
        deposits = exchange_interface.get_deposits(from_timestamp, to_timestamp)
        self.log.debug(deposits)

        if len(deposits) == 0:
            self.log.debug("No new deposits found.")
            return

        self.log.debug("2. Import deposits to Firefly III")
        self.firefly.import_deposits(deposits, firefly_account_collections)


    def handle_withdrawals(self, from_timestamp, to_timestamp, init, exchange_interface,
                        firefly_account_collections):
        self.log_initial_message(from_timestamp, to_timestamp, init, "withdrawals")

        self.log.debug("1. Get received withdrawals from exchange")
        withdrawals = exchange_interface.get_withdrawals(from_timestamp, to_timestamp)

        if len(withdrawals) == 0:
            self.log.debug("No new withdrawals found.")
            return

        self.log.debug("2. Import withdrawals to Firefly III")
        self.firefly.import_withdrawals(withdrawals, firefly_account_collections)


    def handle_interests(self, from_timestamp, to_timestamp, init, exchange_interface,
                        firefly_account_collections):
        self.log_initial_message(from_timestamp, to_timestamp, init, "interests")

        self.log.debug("1. Get received interest from savings from exchange")
        received_interests = exchange_interface.get_savings_interests(from_timestamp, to_timestamp)

        if len(received_interests) == 0:
            self.log.debug("No new interest received.")
            return

        self.log.debug("2. Import received interest to Firefly III")
        firefly_wrapper.import_received_interests(received_interests, firefly_account_collections, self.trading_platform)


    def handle_trades(self, from_timestamp, to_timestamp, init, exchange_interface):
        self.log_initial_message(from_timestamp, to_timestamp, init, "trades")

        self.log.debug("1. Get eligible symbols from existing asset accounts within Firefly III")
        self.log.debug('symbols: ' + str(self.firefly.get_symbols_and_codes()))
        list_of_trading_pairs = exchange_interface.get_trading_pairs(
            self.firefly.get_symbols_and_codes())

        self.log.debug("2. Get trades from crypto currency exchange")
        list_of_trade_data = exchange_interface.get_trades(from_timestamp, to_timestamp, list_of_trading_pairs)
        firefly_account_collections = self.firefly.get_firefly_account_collections_for_pairs(list_of_trading_pairs)

        if len(list_of_trade_data) == 0:
            self.log.debug("No trades to import.")
            are_transactions_to_import = False
        else:
            are_transactions_to_import = True

        if are_transactions_to_import:
            self.log.debug("4. Map transactions to Firefly III accounts and prepare import")
            new_transaction_collections = self.get_transaction_collections_from_trade_data(list_of_trade_data)

            for transaction_collection in new_transaction_collections:
                for firefly_account_collection in firefly_account_collections:
                    self.augment_transaction_collection_with_firefly_accounts(transaction_collection, firefly_account_collection)

                if transaction_collection.from_commission_account is None:
                    raise Exception(f"No commission account found for asset {transaction_collection.trade_data.commission_asset}.")

            self.log.debug("5. Import new trades as transactions to Firefly III")

            for transaction_collection in new_transaction_collections:
                self.firefly.write_new_transaction(transaction_collection)

            self.log.debug("6. Finish import and going to sleep")

        return firefly_account_collections


    def get_x_pub_of_account(self, account, expression):
        try:
            [result] = re.findall(expression, account.attributes.notes)
        except:
            pass
        return result


    def get_transactions_from_blockchain(self, firefly_transactions, supported_blockchains):
        result = {}
        for supported_blockchain in supported_blockchains:
            client = supported_blockchains.get(supported_blockchain)
            for firefly_transaction in firefly_transactions:
                [inner_transaction] = firefly_transaction.attributes.transactions
                if inner_transaction.currency_code == client.get_currency_code() or inner_transaction.currency_symbol == client.get_currency_code():
                    ledger_transaction = client.get_transaction_from_ledger(inner_transaction.external_id)
                    result.setdefault(inner_transaction.external_id, {"firefly": firefly_transaction, "ledger": ledger_transaction, "code": client.get_currency_code()})

        return result


    def handle_unclassified_transactions(self):
        # 1. get accounts with xPub in notes and get addresses from xPub
        supported_blockchains = {}
        for explorer_module in available_explorer:
            supported_blockchains.setdefault(explorer_module.get_blockchain_name(), explorer_module.get_blockchain_explorer())
        account_collections = [
            self.firefly.create_firefly_account_collection(security)
            for security in supported_blockchains.keys()
        ]
        account_address_mapping = {}
        for supported_blockchain in supported_blockchains:
            explorer = supported_blockchains.get(supported_blockchain)
            identifier = explorer.get_address_identifier()
            regular_expression = explorer.get_address_re()
            accounts = self.firefly.get_firefly_accounts_for_crypto_currency(explorer.get_currency_code(), identifier)
            for account in accounts:
                x_pub_of_account = \
                    self.get_x_pub_of_account(account, regular_expression)
                addresses = explorer\
                    .get_tx_addresses_from_address(address=x_pub_of_account)
                account_address_mapping\
                    .setdefault(account.attributes.name, {"addresses": addresses, "account": account.attributes, "code": explorer.get_currency_code()})
        # 2. get transactions with crypto-trades-firefly-iii:unclassified-transaction in notes
        firefly_transactions = self.firefly.get_transactions("unclassified-transaction", supported_blockchains)
        transactions = self.get_transactions_from_blockchain(firefly_transactions, supported_blockchains)
        # 3. rewrite transactions in Firefly-III
        self.firefly.rewrite_unclassified_transactions(transactions, account_address_mapping) #, account_collections)

    def interval_processor(self, from_timestamp, to_timestamp, init):
        exchange_interface = exchange_interface_factory.get_specific_exchange_interface(self.trading_platform)
        trades = self.handle_trades(from_timestamp, to_timestamp, init, exchange_interface)
        # self.handle_interests(from_timestamp, to_timestamp, init, exchange_interface, trades)
        self.handle_withdrawals(from_timestamp, to_timestamp, init, exchange_interface, trades)
        self.handle_deposits(from_timestamp, to_timestamp, init, exchange_interface, trades)
        self.handle_unclassified_transactions()

        return "ok"

    def get_epochs_differences(self, previous_last_begin_timestamp, last_begin_timestamp, interval: IntervalEnum):
        if interval == IntervalEnum.HOURLY:
            return int(last_begin_timestamp / 1000 / 60 / 60) - int(previous_last_begin_timestamp / 1000 / 60 / 60)
        elif interval == IntervalEnum.DAILY:
            return int(last_begin_timestamp / 1000 / 60 / 60 / 24) - int(
                previous_last_begin_timestamp / 1000 / 60 / 60 / 24)
        elif interval == IntervalEnum.DEBUG:
            return int(last_begin_timestamp / 1000 / 10) - int(previous_last_begin_timestamp / 1000 / 10)
        else:
            self.log.error("The configured interval is not supported. Use 'hourly' or 'daily' within your config.")
            exit(-749)
