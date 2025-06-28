from dotenv import load_dotenv, dotenv_values
import logging

load_dotenv()

config = dotenv_values()

debug = config.get('DEBUG', False)

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


firefly_host = config['FIREFLY_HOST']
firefly_verify_ssl = get_env_bool('FIREFLY_VALIDATE_SSL')
firefly_access_token = config['FIREFLY_ACCESS_TOKEN']

sync_begin_timestamp = config['SYNC_BEGIN_TIMESTAMP']
sync_inverval = config['SYNC_TRADES_INTERVAL']

# Set up root logger level based on debug
if debug:
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
else:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
