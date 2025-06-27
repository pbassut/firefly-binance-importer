from dotenv import load_dotenv
load_dotenv()  # This loads variables from .env into os.environ

import time
import backends.exchanges as exchanges

from backends.firefly import firefly_wrapper
import migrate_firefly_identifiers
from importer.sync_timer import SyncTimer
import logging

import config

logger = logging.getLogger(__name__)

firefly = firefly_wrapper.FireflyWrapper("binance")

def start():
    migrate_firefly_identifiers.migrate_identifiers()
    try:
        impl_meta_class_instances = exchanges.get_impl_meta_class_instances()
        worker(impl_meta_class_instances)
    except Exception as e:
        logger.error(str(e), exc_info=config.debug)


def worker(meta_class_instances):
    if not firefly.connect():
        exit(-12)

    interval_seconds = 0
    if config.sync_inverval == 'hourly':
        interval_seconds = 3600
    elif config.sync_inverval == 'daily':
        interval_seconds = 3600 * 24
    elif config.sync_inverval == 'debug':
        interval_seconds = 10
    else:
        logger.error("The configured interval is not supported. Use 'hourly' or 'daily' within your config.")
        exit(-749)

    exchanges_list = []

    for meta_class in meta_class_instances:
        exchanges_list.append({
            'name': meta_class.get_exchange_name(),
            'timer_object': SyncTimer(meta_class.get_exchange_name()) if meta_class.is_enabled() else None
        })

    exchanges_available = False
    for exchange in exchanges_list:
        if exchange.get('timer_object') is not None:
            exchanges_available = True

    if not exchanges_available:
        logger.error("There are no exchanges configured. Exit!")
        exit(0)

    for exchange in exchanges_list:
        if exchange.get('timer_object') is None:
            continue
        exchange.get('timer_object').initial_sync()

    while True:
        time.sleep(interval_seconds)
        for exchange in exchanges_list:
            if exchange.get('timer_object') is None:
                continue
            exchange.get('timer_object').sync()


start()
