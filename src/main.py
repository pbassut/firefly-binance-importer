import config
import time
import backends.exchanges as exchanges

from backends.firefly import firefly_wrapper
import migrate_firefly_identifiers
from importer.sync_logic import IntervalEnum
from importer.sync_timer import SyncTimer
import logging


logger = logging.getLogger(__name__)

firefly = firefly_wrapper.FireflyWrapper("binance")

def start():
    # migrate_firefly_identifiers.migrate_identifiers()
    try:
        impl_meta_class_instances = exchanges.get_impl_meta_class_instances()
        worker(impl_meta_class_instances)
    except Exception as e:
        logger.error(str(e), exc_info=config.debug)


def worker(meta_class_instances):
    if not firefly.connect():
        logger.error('Failed to connect to Firefly III. Exit!')
        exit(-12)

    interval_seconds = 0
    if config.sync_inverval == IntervalEnum.HOURLY.value:
        interval_seconds = 3600
    elif config.sync_inverval == IntervalEnum.DAILY.value:
        interval_seconds = 3600 * 24
    elif config.sync_inverval == IntervalEnum.DEBUG.value:
        interval_seconds = 10
    else:
        logger.error("The configured interval is not supported. Use 'hourly' or 'daily' within your config.")
        exit(-749)

    if all(map(lambda exchange: exchange.is_enabled(), meta_class_instances)):
        logger.error("There are no exchanges configured. Exit!")
        exit(0)

    exchanges_list = []
    for cls in meta_class_instances:
        if not cls.is_enabled():
            continue

        exchange_name = cls.get_exchange_name()
        exchanges_list.append({ 'name': exchange_name, 'syncer': SyncTimer(exchange_name) })

    for exchange in exchanges_list:
        exchange.get('syncer').initial_sync()

    while True:
        logger.info('Sleeping for %d seconds', interval_seconds)
        time.sleep(interval_seconds)

        for exchange in exchanges_list:
            logger.info('Syncing %s', exchange.get('name'))
            exchange.get('syncer').sync()

start()
