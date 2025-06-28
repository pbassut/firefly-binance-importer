import config as config
import datetime
from importer.sync_logic import SyncLogic
from backends.exchanges.exchange_interface import ExchangeUnderMaintenanceException
import logging


class SyncTimer(object):
    last_sync_result = None
    last_sync_interval_begin_timestamp = None

    def __init__(self, trading_platform):
        self.trading_platform = trading_platform

    def initial_sync(self):
        self.log = logging.getLogger(self.trading_platform + " [SYNC_TIMER]")
        self.log.debug('Initializing trade import from crypto exchange to Firefly III')

        begin_of_sync_timestamp = config.sync_begin_timestamp
        self.sync_logic = SyncLogic(self.trading_platform)

        try:
            self.last_sync_interval_begin_timestamp = self.import_all_from_exchange()
        except ExchangeUnderMaintenanceException as maintenance:
            self.log.debug("Exchange under maintenance. Delaying import of all movements.")
            self.last_sync_interval_begin_timestamp = datetime.datetime.fromisoformat(begin_of_sync_timestamp)\
                                                          .timestamp() * 1000
        self.last_sync_result = 'ok'

        return

    def sync(self):
        if self.last_sync_interval_begin_timestamp is None:
            self.log.error("SYNC: The sync was not initialized properly")
            exit(-700)
        if self.last_sync_result is None or not str(self.last_sync_result).lower() == 'ok':
            self.log.error("SYNC: The last sync did not finish successful: " + str(self.last_sync_result))
            exit(-700)

        self.sync_interval(self.last_sync_interval_begin_timestamp, config.sync_inverval)

    def sync_interval(self, begin_timestamp_in_millis, interval):
        now = datetime.datetime.now()

        self.log.debug("Now: " + str(datetime.datetime.now()))
        self.log.debug("Last Interval Begin: " + str(datetime.datetime.fromtimestamp(begin_timestamp_in_millis / 1000)))

        previous_last_sync_interval_begin_timestamp = self.last_sync_interval_begin_timestamp
        new_to_timestamp_in_millis = self.get_last_interval_begin_millis(config.sync_inverval, now)

        try:
            self.last_sync_result = self.sync_logic.interval_processor(previous_last_sync_interval_begin_timestamp, new_to_timestamp_in_millis, False)
            self.last_sync_interval_begin_timestamp = new_to_timestamp_in_millis
        except ExchangeUnderMaintenanceException as maintenance:
            self.log.debug("Exchange under maintenance. Delaying import of movements.")

    def get_last_interval_begin_millis(self, interval, current_datetime):
        if interval == 'hourly':
            epoch_counter = int(current_datetime.timestamp() / (60 * 60))
            last_epoch = epoch_counter - 1
            return last_epoch * 60 * 60 * 1000
        elif interval == 'daily':
            epoch_counter = int(current_datetime.timestamp() / (60 * 60 * 24))
            last_epoch = epoch_counter - 1
            return last_epoch * 60 * 60 * 24 * 1000
        elif interval == 'debug':
            epoch_counter = int(current_datetime.timestamp() / 10)
            return epoch_counter * 10 * 1000
        else:
            self.log.error("The configured interval is not supported. Use 'hourly' or 'daily' within your config.")
            exit(-749)

    def import_all_from_exchange(self):
        now = datetime.datetime.now()
        to_timestamp = self.get_last_interval_begin_millis(config.sync_inverval, now)
        begin_timestamp = int(datetime.datetime.fromisoformat(config.sync_begin_timestamp).timestamp() * 1000)
        self.sync_logic.interval_processor(begin_timestamp, to_timestamp, True)

        return to_timestamp
