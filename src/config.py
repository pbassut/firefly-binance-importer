from dotenv import load_dotenv, dotenv_values
import logging

load_dotenv()

config = dotenv_values()


def get_env_bool(env_var_name, default=True) -> bool:
    value = config.get(env_var_name)
    if value is None:
        return default
    value = value.strip().lower()
    if value in ('1', 'true', 'yes', 'on'):
        return True
    if value in ('0', 'false', 'no', 'off'):
        return False
    return default


debug = get_env_bool('DEBUG', False)
firefly_host = config['FIREFLY_HOST']
firefly_verify_ssl = get_env_bool('FIREFLY_VALIDATE_SSL')
firefly_access_token = config['FIREFLY_ACCESS_TOKEN']

sync_begin_timestamp = config['SYNC_BEGIN_TIMESTAMP']
sync_inverval = config['SYNC_TRADES_INTERVAL']

logging.basicConfig(level=logging.DEBUG if debug else logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
