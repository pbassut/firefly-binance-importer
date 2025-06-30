from __future__ import print_function

import datetime
import hashlib
from typing import List

import firefly_iii_client
import urllib3
from firefly_iii_client import ApiException, TransactionTypeProperty

import config

from model.savings import InterestDue
from model.transaction import TransactionType
from model.withdrawal_deposit import WithdrawalData, DepositData

import logging

from backends.firefly.transaction_collection import TransactionCollection
from backends.firefly.account_collection import AccountCollection

# Set up logger for this module
logger = logging.getLogger(__name__)

urllib3.disable_warnings()

firefly_config = None

SERVICE_IDENTIFICATION = "crypto-trades-firefly-iii"

def api(func):
    def wrapper(*args, **kwargs):
        with firefly_iii_client.ApiClient(firefly_config) as api_client:
            return func(args[0], api_client, *args[1:], **kwargs)
    return wrapper

def api_service(service_class: type):
    def wrapper(func):
        def wrapper(*args, **kwargs):
            with firefly_iii_client.ApiClient(firefly_config) as api_client:
                return func(args[0], service_class(api_client), *args[1:], **kwargs)
        return wrapper
    return wrapper

class FireflyWrapper:
    def __init__(self, trading_platform):
        self.log = logging.getLogger("[" + trading_platform.upper() + "] [FIREFLY_WRAPPER]")
        self.trading_platform = trading_platform

    def default_key(self, key=None):
        if key is None:
            return ':'.join([SERVICE_IDENTIFICATION, self.trading_platform.lower()])

        return ':'.join([SERVICE_IDENTIFICATION, key, self.trading_platform.lower()])

    def get_acc_fund_key(self):
        return self.default_key()

    def get_acc_revenue_key(self):
        return self.default_key()

    def get_acc_expenses_key(self):
        return self.default_key()

    def get_tr_trade_key(self):
        return self.default_key()

    def get_tr_fee_key(self):
        return self.default_key()

    def get_withdrawal_classified_key(self):
        return self.default_key()

    def get_deposit_classified_key(self):
        return self.default_key()

    def get_withdrawal_unclassified_key(self):
        return SERVICE_IDENTIFICATION + ":unclassified-transaction:" + self.trading_platform.lower()

    def get_deposit_unclassified_key(self):
        return SERVICE_IDENTIFICATION + ":unclassified-transaction:" + self.trading_platform.lower()

    def connect(self):
        global firefly_config
        if firefly_config is not None:
            return True

        try:
            logger.info('--------------------------------------------------------')
            logger.info('Trying to connect to your Firefly III account...')

            firefly_iii_client.configuration.verify_ssl = False

            configuration = firefly_iii_client.configuration.Configuration(
                host=config.firefly_host
            )

            configuration.verify_ssl = config.firefly_verify_ssl
            configuration.access_token = config.firefly_access_token

            with firefly_iii_client.ApiClient(configuration) as api_client:
                about = firefly_iii_client.AboutApi(api_client).get_about()
                logger.info(f"Connected to Firefly III {about.data.version}")

            logger.info('Connection to your Firefly III account established.')
            logger.info('--------------------------------------------------------')
            firefly_config = configuration
            return True
        except Exception as e:
            logger.error("Cannot get data from server. Check the connection or your access token configuration.", exc_info=config.debug)
            exit(-600)


    @api_service(firefly_iii_client.AccountsApi)
    def get_symbols_and_codes(self, accounts_api: firefly_iii_client.AccountsApi):
        asset_accounts = []

        try:
            accounts = []

            paging = True
            page = 1
            while paging:
                get_accounts_response = accounts_api.list_account(page=page)

                accounts.extend(get_accounts_response.data)

                if get_accounts_response.meta.pagination.total_pages > page:
                    page += 1
                else:
                    paging = False

            for account in accounts:
                if account.attributes.type == 'asset':
                    asset_accounts.append(account)

            list_of_symbols_and_codes = []
            relevant_accounts = []

            notes_identifier = self.get_acc_fund_key()

            for account in asset_accounts:
                notes = account.attributes.notes
                if notes is not None:
                    if notes_identifier in notes:
                        relevant_accounts.append(account)

            logger.info(f"{self.trading_platform}: {len(relevant_accounts)} relevant accounts found within your Firefly III instance.")
            for relevant_account in relevant_accounts:
                logger.info(f'{self.trading_platform}:   - "{relevant_account.attributes.name}"')

            for account in relevant_accounts:
                if not any(account.attributes.currency_code in s for s in list_of_symbols_and_codes):
                    list_of_symbols_and_codes.append(account.attributes.currency_code if account.attributes.currency_code != 'OPC' else 'OP')
                if not any(account.attributes.currency_symbol in s for s in list_of_symbols_and_codes):
                    list_of_symbols_and_codes.append(account.attributes.currency_symbol if account.attributes.currency_symbol != 'OPC' else 'OP')

            return list_of_symbols_and_codes
        except Exception as e:
            logger.error('There was an error getting the accounts', exc_info=config.debug)
            exit(-601)


    @api_service(firefly_iii_client.TransactionsApi)
    def write_new_received_interest_as_transaction(self, tx_api: firefly_iii_client.TransactionsApi, received_interest, account_collection):
        list_inner_transactions = []

        currency_code = account_collection.asset_account.attributes.currency_code
        currency_symbol = account_collection.asset_account.attributes.currency_symbol
        amount = received_interest.amount
        description = self.trading_platform + " | INTEREST | Currency: " + currency_code

        if received_interest.due == InterestDue.DAILY:
            description += " | Daily interest"
        elif received_interest.due == InterestDue.ACTIVE:
            description += " | Active interest"
        elif received_interest.due == InterestDue.FIXED:
            description += " | Locked interest"

        tags = [self.trading_platform.lower()]
        if config.debug:
            tags.append('dev')

        split = firefly_iii_client.TransactionSplitStore(
            amount=amount,
            date=received_interest.date,
            description=description,
            type='deposit',
            tags=tags,
            reconciled=True,
            source_name=account_collection.revenue_account.attributes.name,
            source_type=account_collection.revenue_account.attributes.type,
            currency_code=currency_code,
            currency_symbol=currency_symbol,
            destination_name=account_collection.asset_account.attributes.name,
            destination_type=account_collection.asset_account.attributes.type,
            external_id=account_collection.trade_data.id,
            notes=self.get_acc_revenue_key()
        )
        # split.import_hash_v2 = hash_transaction(split.amount, split.date, split.description, "", split.source_name, split.destination_name, split.tags)
        list_inner_transactions.append(split)
        new_transaction = firefly_iii_client.TransactionStore(apply_rules=False, transactions=list_inner_transactions, error_if_duplicate_hash=True)

        try:
            logger.info(f"{self.trading_platform}:   - Writing a new received interest.")
            tx_api.store_transaction(new_transaction)
        except ApiException as e:
            if e.status == 422 and "Duplicate of transaction" in e.body:
                logger.warning(f"{self.trading_platform}:   - Duplicate received interest detected.")
            else:
                message: str = f"{self.trading_platform}:   - There was an unknown error writing a new received interest."
                logger.error(message, exc_info=config.debug)
        except Exception as e:
            message: str = f"{self.trading_platform}:   - There was an unknown error writing a new received interest."
            logger.error(message, exc_info=config.debug)


    @api_service(firefly_iii_client.TransactionsApi)
    def write_commission(self, tx_api: firefly_iii_client.TransactionsApi, transaction_collection: TransactionCollection):
        list_inner_transactions = []

        currency_code = transaction_collection.from_commission_account.currency_code
        currency_symbol = transaction_collection.from_commission_account.currency_symbol
        amount = transaction_collection.trade_data.commission_amount
        description = self.trading_platform + " | FEE | Currency: " + currency_code

        tags = [self.trading_platform.lower()]
        if config.debug:
            tags.append('dev')

        split = firefly_iii_client.TransactionSplitStore(
            amount=amount,
            date=datetime.datetime.fromtimestamp(int(transaction_collection.trade_data.time / 1000)),
            description=description,
            type='withdrawal',
            tags=tags,
            reconciled=True,
            source_name=transaction_collection.from_commission_account.name,
            source_type=transaction_collection.from_commission_account.type,
            currency_code=currency_code,
            currency_symbol=currency_symbol,
            destination_name=transaction_collection.commission_account.name,
            destination_type=transaction_collection.commission_account.type,
            external_id=str(transaction_collection.trade_data.id),
            notes=self.get_tr_fee_key()
        )
        # split.import_hash_v2 = hash_transaction(split.amount, split.date, split.description, split.external_id, split.source_name, split.destination_name, split.tags)
        list_inner_transactions.append(split)
        new_transaction = firefly_iii_client.TransactionStore(apply_rules=False, transactions=list_inner_transactions, error_if_duplicate_hash=True)

        try:
            tx_api.store_transaction(new_transaction)
            logger.info(f"Successfully wrote a new paid commission #{transaction_collection.trade_data.id}")
        except ApiException as e:
            if e.status == 422 and "Duplicate of transaction" in e.body:
                logger.debug(f"Duplicate commission transaction #{transaction_collection.trade_data.id}")
            else:
                message: str = f"There was an unknown error writing a new paid commission. Here's the trade id: '{transaction_collection.trade_data.id}'"
                logger.error(message, exc_info=config.debug)


    def hash_unclassifiable(self, amount, date, external_id, currency_code: str, tags: List[str]):
        hashed_result = str(amount) + str(date) + str(external_id) + self.trading_platform + currency_code
        for tag in tags:
            hashed_result += tag
        hash_object = hashlib.sha256(hashed_result.encode())
        hex_dig = hash_object.hexdigest()
        return hex_dig


    def hash_transaction(self, amount, date, description, external_id, source_name, destination_name, tags):
        hashed_result = str(amount) + str(date) + description + str(external_id) + source_name + destination_name
        for tag in tags:
            hashed_result += tag
        hash_object = hashlib.sha256(hashed_result.encode())
        hex_dig = hash_object.hexdigest()
        return hex_dig



    @api_service(firefly_iii_client.AccountsApi)
    def get_accounts_from_firefly(self, accounts_api: firefly_iii_client.AccountsApi, supported_blockchain, account_type, notes_keywords):
        result = []
        try:
            accounts = []
            page = 0
            load_again = True
            while load_again:
                new_accounts = accounts_api.list_account(page=page).data
                accounts.extend(new_accounts)
                if len(new_accounts) < 50:
                    load_again = False
                else:
                    page += 1

            for account in accounts:
                if account.attributes.type == account_type and \
                        account.attributes.notes is not None and \
                        notes_keywords in account.attributes.notes and \
                        (account.attributes.currency_code == supported_blockchain or
                        account.attributes.currency_symbol == supported_blockchain):
                    result.append(account)
        except Exception:
            logger.error('There was an error getting the accounts from Firefly III', exc_info=config.debug)
            exit(-604)
        return result


    @api_service(firefly_iii_client.TransactionsApi)
    def get_transactions(self, tx_api: firefly_iii_client.TransactionsApi, notes_keyword, supported_blockchains):
        result = []
        try:
            transactions = []
            page = 0
            load_next = True
            while load_next:
                next_transactions = tx_api.list_transaction(type="all", page=page).data
                transactions.extend(next_transactions)
                if len(next_transactions) < 50:
                    load_next = False
                else:
                    page += 1
            for transaction in transactions:
                for inner_transaction in transaction.attributes.transactions:
                    if inner_transaction.notes is not None and \
                            notes_keyword in inner_transaction.notes and \
                            (any(inner_transaction.currency_code == supported_blockchains.get(s).get_currency_code() for s in supported_blockchains) or
                            any(inner_transaction.currency_symbol == supported_blockchains.get(s).get_currency_code() for s in supported_blockchains)):
                        result.append(transaction)
                        break
        except Exception as e:
            logger.error('There was an error getting the transactions from Firefly III', exc_info=config.debug)
            exit(-604)
        return result


    @api_service(firefly_iii_client.AccountsApi)
    def get_account_from_firefly(self, accounts_api: firefly_iii_client.AccountsApi, security, account_type, notes_keywords):
        try:
            accounts = accounts_api.list_account().data

            for account in accounts:
                if account.attributes.type == account_type and \
                        account.attributes.notes is not None and \
                        notes_keywords in account.attributes.notes:
                    if security is None:
                        return account
                    else:
                        if account.attributes.currency_code == security or account.attributes.currency_symbol == security:
                            return account
        except Exception as e:
            logger.error('There was an error getting the accounts from Firefly III', exc_info=config.debug)
            exit(-604)
        return None

    def get_firefly_accounts_for_crypto_currency(self, supported_blockchain, identifier):
        return self.get_accounts_from_firefly(supported_blockchain, 'asset', identifier)

    def get_asset_account_for_security(self, security):
        return self.get_account_from_firefly(security, 'asset', self.get_acc_fund_key())

    def get_expense_account_for_security(self, security):
        return self.get_account_from_firefly(None, 'expense', self.get_acc_expenses_key())

    def get_revenue_account_for_security(self, security):
        return self.get_account_from_firefly(None, 'revenue', self.get_acc_revenue_key())

    def create_firefly_account_collection(self, security):
        asset_account = self.get_asset_account_for_security(security)
        if asset_account is None:
            raise Exception(f"No asset account found with tag {self.get_acc_fund_key()}. Create one before proceeding.")

        expense_account = self.get_expense_account_for_security(security)
        if expense_account is None:
            raise Exception(f"No expense account found with tag {self.get_acc_expenses_key()}. Create one before proceeding.")

        revenue_account = self.get_revenue_account_for_security(security)
        if revenue_account is None:
            raise Exception(f"No revenue account found with tag {self.get_acc_revenue_key()}. Create one before proceeding.")

        return AccountCollection(security, asset_account, expense_account, revenue_account)

    def get_firefly_account_collections_for_pairs(self, list_of_trading_pairs):
        result = []

        relevant_securities = []
        for trading_pair in list_of_trading_pairs:
            if any(trading_pair.security in s for s in relevant_securities):
                continue
            relevant_securities.append(trading_pair.security)
        for trading_pair in list_of_trading_pairs:
            if any(trading_pair.currency in s for s in relevant_securities):
                continue
            relevant_securities.append(trading_pair.currency)
        for relevant_security in relevant_securities:
            result.append(self.create_firefly_account_collection(relevant_security))

        return result

    def import_received_interests(self, received_interests, firefly_account_collections):
        for received_interest in received_interests:
            for account_collection in firefly_account_collections:
                if received_interest.currency == account_collection.security:
                    self.write_new_received_interest_as_transaction(received_interest, account_collection)



    def import_withdrawals(self, withdrawals: List[WithdrawalData], firefly_account_collections):
        for withdrawal in withdrawals:
            for account_collection in firefly_account_collections:
                if withdrawal.asset == account_collection.security:
                    self.write_new_withdrawal(withdrawal, account_collection)



    def import_deposits(self, deposits, firefly_account_collections):
        for deposit in deposits:
            for account_collection in firefly_account_collections:
                if deposit.asset == account_collection.security:
                    self.write_new_deposit(deposit, account_collection)


    def get_relevant_firefly_deposit_account(self, transaction_data, account_address_mapping):
        for account_name in account_address_mapping:
            account_mapping = account_address_mapping.get(account_name)
            if not account_mapping.get("code") == transaction_data.get("firefly").attributes.transactions[0].currency_code and not account_mapping.get("code") == transaction_data.get("firefly").attributes.transactions[0].currency_symbol:
                continue
            for firefly_address in account_mapping.get("addresses"):
                for ledger_addresses in transaction_data.get("ledger").ins:
                    if firefly_address == ledger_addresses:
                        return account_mapping
        return None


    def get_relevant_firefly_withdrawal_account(self, transaction_data, account_address_mapping):
        for account_name in account_address_mapping:
            account_mapping = account_address_mapping.get(account_name)
            if not account_mapping.get("code") == transaction_data.get("firefly").attributes.transactions[0].currency_code and not account_mapping.get("code") == transaction_data.get("firefly").attributes.transactions[0].currency_symbol:
                continue
            for firefly_address in account_mapping.get("addresses"):
                for ledger_addresses in transaction_data.get("ledger").outs:
                    if firefly_address == ledger_addresses:
                        return account_mapping
        return None

    @api_service(firefly_iii_client.TransactionsApi)
    def write_new_transaction(self, tx_api: firefly_iii_client.TransactionsApi, transaction_collection):
            list_inner_transactions = []
            if transaction_collection.trade_data.type == TransactionType.BUY:
                type_string = "BUY"
            else:
                type_string = "SELL"

            if type_string == "BUY":
                currency_code = transaction_collection.from_ff_account.currency_code
                currency_symbol = transaction_collection.from_ff_account.currency_symbol
                foreign_currency_code = transaction_collection.to_ff_account.currency_code
                foreign_currency_symbol = transaction_collection.to_ff_account.currency_symbol
            else:
                currency_code = transaction_collection.from_ff_account.currency_code
                currency_symbol = transaction_collection.from_ff_account.currency_symbol
                foreign_currency_code = transaction_collection.to_ff_account.currency_code
                foreign_currency_symbol = transaction_collection.to_ff_account.currency_symbol

            amount = transaction_collection.trade_data.security_amount
            foreign_amount = float(transaction_collection.trade_data.currency_amount)
            tags = [self.trading_platform.lower()]
            if config.debug:
                tags.append('dev')
            description = self.trading_platform + ' | ' + type_string + " | Security: " + transaction_collection.trade_data.trading_pair.security + " | Currency: " + transaction_collection.trade_data.trading_pair.currency + " | Ticker " + transaction_collection.trade_data.trading_pair.security + transaction_collection.trade_data.trading_pair.currency

            split = firefly_iii_client.TransactionSplitStore(
                amount=amount,
                date=datetime.datetime.fromtimestamp(int(transaction_collection.trade_data.time / 1000)),
                description=description,
                type=TransactionTypeProperty.TRANSFER,
                tags=tags,
                reconciled=True,
                source_name=transaction_collection.from_ff_account.name,
                source_type=transaction_collection.from_ff_account.type,
                currency_code=currency_code,
                currency_symbol=currency_symbol,
                destination_name=transaction_collection.to_ff_account.name,
                destination_type=transaction_collection.to_ff_account.type,
                foreign_currency_code=foreign_currency_code,
                foreign_currency_symbol=foreign_currency_symbol,
                foreign_amount='{:.8f}'.format(foreign_amount),
                external_id=str(transaction_collection.trade_data.id),
                notes=self.get_tr_fee_key()
            )
            # split.import_hash_v2 = hash_transaction(split.amount, split.var_date, split.description, split.external_id, split.source_name, split.destination_name, split.tags)
            list_inner_transactions.append(split)
            new_transaction = firefly_iii_client.TransactionStore(apply_rules=False, transactions=list_inner_transactions, error_if_duplicate_hash=True)

            try:
                tx_api.store_transaction(new_transaction)
                self.write_commission(transaction_collection)
                logger.info(f"Successfully wrote a new trade #'{transaction_collection.trade_data.id}'")
            except ApiException as e:
                if e.status == 422 and "Duplicate of transaction" in e.body:
                    logger.debug(f"Duplicated transaction #{transaction_collection.trade_data.id}")
                else:
                    message: str = f"Unknown error when writing a new trade #'{transaction_collection.trade_data.id}'"
                    logger.error(message, exc_info=config.debug)

    @api_service(firefly_iii_client.TransactionsApi)
    def write_new_withdrawal(self, tx_api: firefly_iii_client.TransactionsApi, withdrawal, account_collection):
        list_inner_transactions = []
        currency_code = account_collection.asset_account.attributes.currency_code
        currency_symbol = account_collection.asset_account.attributes.currency_symbol
        amount = withdrawal.amount
        tags = [self.trading_platform.lower()]
        description = self.trading_platform + " | WITHDRAWAL (unclassified) | Security: " + withdrawal.asset

        split = firefly_iii_client.TransactionSplitStore(
            amount=amount,
            date=datetime.datetime.fromtimestamp(int(withdrawal.timestamp / 1000)),
            description=description,
            type=TransactionTypeProperty.WITHDRAWAL,
            tags=tags,
            reconciled=True,
            source_name=account_collection.asset_account.attributes.name,
            source_type=account_collection.asset_account.attributes.type,
            currency_code=currency_code,
            currency_symbol=currency_symbol,
            destination_name=account_collection.expense_account.attributes.name,
            destination_type=account_collection.expense_account.attributes.type,
            external_id=str(withdrawal.transaction_id),
            notes=self.get_withdrawal_unclassified_key()
        )
        # split.import_hash_v2 = hash_unclassifiable(split.amount, split.date, split.external_id, trading_platform, currency_code, split.tags)
        list_inner_transactions.append(split)
        new_transaction = firefly_iii_client.TransactionStore(apply_rules=False, transactions=list_inner_transactions, error_if_duplicate_hash=True)

        try:
            logger.info(f"Writing a new withdrawal.")
            tx_api.store_transaction(new_transaction)
        except ApiException as e:
            if e.status == 422 and "Duplicate of transaction" in e.body:
                logger.warning(f"Duplicate withdrawal transaction detected. Here's the transaction id: '{withdrawal.transaction_id}'")
            else:
                message: str = f"There was an unknown error writing a new withdrawal. Here's the transaction id: '{withdrawal.transaction_id}'"
                logger.error(message, exc_info=config.debug)


    @api_service(firefly_iii_client.TransactionsApi)
    def write_new_deposit(self, tx_api: firefly_iii_client.TransactionsApi, deposit: DepositData, account_collection):
        list_inner_transactions = []
        currency_code = account_collection.asset_account.attributes.currency_code
        currency_symbol = account_collection.asset_account.attributes.currency_symbol
        amount = deposit.amount
        tags = [self.trading_platform.lower()]
        description = self.trading_platform + " | DEPOSIT (unclassified) | Security: " + deposit.asset

        split = firefly_iii_client.TransactionSplitStore(
            amount=amount,
            date=datetime.datetime.fromtimestamp(int(deposit.timestamp / 1000)),
            description=description,
            type=TransactionTypeProperty.DEPOSIT,
            tags=tags,
            reconciled=True,
            source_name=account_collection.revenue_account.attributes.name,
            source_type=account_collection.revenue_account.attributes.type,
            currency_code=currency_code,
            currency_symbol=currency_symbol,
            destination_name=account_collection.asset_account.attributes.name,
            destination_type=account_collection.asset_account.attributes.type,
            external_id=deposit.transaction_id,
            notes=self.get_withdrawal_unclassified_key()
        )
        # split.import_hash_v2 = hash_unclassifiable(split.amount, split.date, split.external_id, trading_platform, currency_code, split.tags)
        list_inner_transactions.append(split)
        new_transaction = firefly_iii_client.TransactionStore(apply_rules=False, transactions=list_inner_transactions, error_if_duplicate_hash=True)

        try:
            logger.info(f"Writing a new deposit.")
            tx_api.store_transaction(new_transaction)
        except ApiException as e:
            if e.status == 422 and "Duplicate of transaction" in e.body:
                logger.warning(f"{self.trading_platform}:   - Duplicate deposit transaction detected. Here's the trade id: '{deposit.transaction_id}'")
            else:
                message: str = f"There was an unknown error writing a new deposit. Here's the transaction id: '{deposit.transaction_id}'"
                logger.error(message, exc_info=config.debug)


    @api_service(firefly_iii_client.TransactionsApi)
    def rewrite_unclassified_deposit_transaction(self, tx_api: firefly_iii_client.TransactionsApi, transaction_data, relevant_firefly_account):
            list_inner_transactions = []

            [inner_transaction] = transaction_data.get("firefly").attributes.transactions

            tags = inner_transaction.tags
            if config.debug:
                tags.append('dev')
            description = self.trading_platform + " | DEPOSIT | Security: " + transaction_data.get("code")

            split = firefly_iii_client.TransactionSplitStore(
                amount=inner_transaction.amount,
                date=inner_transaction.date,
                description=description,
                type=TransactionTypeProperty.TRANSFER,
                tags=tags,
                reconciled=True,
                source_name=relevant_firefly_account.get("account").name,
                source_type=relevant_firefly_account.get("account").type,
                currency_code=inner_transaction.currency_code,
                currency_symbol=inner_transaction.currency_symbol,
                destination_name=inner_transaction.destination_name,
                destination_type=inner_transaction.destination_type,
                external_id=inner_transaction.external_id,
                notes=self.get_withdrawal_classified_key()
            )
            # split.import_hash_v2 = hash_unclassifiable(float(split.amount), split.date, split.external_id, trading_platform, split.currency_code, split.tags)
            list_inner_transactions.append(split)
            new_transaction = firefly_iii_client.TransactionStore(apply_rules=False, transactions=list_inner_transactions, error_if_duplicate_hash=True)

            try:
                logger.info(f"Rewriting a deposit.")
                tx_api.delete_transaction(transaction_data.get("firefly").id)
                tx_api.store_transaction(new_transaction)
            except ApiException as e:
                if e.status == 422 and "Duplicate of transaction" in e.body:
                    logger.warning(f"Duplicate deposit transaction detected. Here's the external id: '{inner_transaction.external_id}'")
                else:
                    message: str = f"There was an unknown error rewriting a deposit. Here's the external id: '{inner_transaction.external_id}'"
                    logger.error(message, exc_info=config.debug)
            except Exception as e:
                message: str = f"There was an unknown error rewriting a deposit. Here's the external id: '{inner_transaction.external_id}'"
                logger.error(message, exc_info=config.debug)


    @api_service(firefly_iii_client.TransactionsApi)
    def rewrite_unclassified_withdrawal_transaction(self, tx_api: firefly_iii_client.TransactionsApi, transaction_data, relevant_firefly_account):
        list_inner_transactions = []

        [inner_transaction] = transaction_data.get("firefly").attributes.transactions

        tags = inner_transaction.tags
        if config.debug:
            tags.append('dev')
        description = self.trading_platform + " | WITHDRAWAL | Security: " + transaction_data.get("code")

        split = firefly_iii_client.TransactionSplitStore(
            amount=inner_transaction.amount,
            date=inner_transaction.date,
            description=description,
            type=TransactionTypeProperty.TRANSFER,
            tags=tags,
            reconciled=True,
            source_name=inner_transaction.source_name,
            source_type=inner_transaction.source_type,
            currency_code=inner_transaction.currency_code,
            currency_symbol=inner_transaction.currency_symbol,
            destination_name=relevant_firefly_account.get("account").name,
            destination_type=relevant_firefly_account.get("account").type,
            external_id=inner_transaction.external_id,
            notes=self.get_withdrawal_classified_key()
        )
        # split.import_hash_v2 = hash_unclassifiable(float(split.amount), split.date, split.external_id, trading_platform, split.currency_code, split.tags)
        list_inner_transactions.append(split)
        new_transaction = firefly_iii_client.TransactionStore(apply_rules=False, transactions=list_inner_transactions, error_if_duplicate_hash=True)

        try:
            logger.info(f"Rewriting a withdrawal.")
            tx_api.delete_transaction(transaction_data.get("firefly").id)
            tx_api.store_transaction(new_transaction)
        except ApiException as e:
            if e.status == 422 and "Duplicate of transaction" in e.body:
                logger.warning(f"Duplicate withdrawal transaction detected. Here's the external id: '{inner_transaction.external_id}'")
            else:
                message: str = f"There was an unknown error rewriting a withdrawal. Here's the external id: '{inner_transaction.external_id}'"
                logger.error(message, exc_info=config.debug)    
        except Exception as e:
            message: str = f"There was an unknown error rewriting a withdrawal. Here's the external id: '{inner_transaction.external_id}'"
            logger.error(message, exc_info=config.debug)


    def rewrite_unclassified_transactions(self, transactions, account_address_mapping):
        logger.info("Rewriting %d deposits/withdrawals.", len(transactions))

        for transaction in transactions:
            transaction_data = transactions.get(transaction)
            [inner_transaction] = transaction_data.get("firefly").attributes.transactions
            if self.trading_platform + " | DEPOSIT (unclassified) | Security: " in inner_transaction.description:
                relevant_firefly_account = self.get_relevant_firefly_deposit_account(transaction_data, account_address_mapping)
                self.rewrite_unclassified_deposit_transaction(transaction_data, relevant_firefly_account)
            elif self.trading_platform + " | WITHDRAWAL (unclassified) | Security: " in inner_transaction.description:
                relevant_firefly_account = self.get_relevant_firefly_withdrawal_account(transaction_data, account_address_mapping)
                self.rewrite_unclassified_withdrawal_transaction(transaction_data, relevant_firefly_account)

