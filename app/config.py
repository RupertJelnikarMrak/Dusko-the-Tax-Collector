import logging
from dotenv import load_dotenv
import os

load_dotenv()

def get_env_variable(var_name):
    try:
        return os.environ[var_name]
    except KeyError:
        error_msg = f'Set the {var_name} environment variable'
        raise KeyError(error_msg)

DISCORD_AUTH_TOKEN = get_env_variable("DISCORD_AUTH_TOKEN")

BOT_PREFIX = '+'

DATABASE_URL = get_env_variable("DATABASE_URL").replace("postgresql://", "postgresql+asyncpg://")

def setup_logging():
    levelname = "[ {levelname} ]"
    asctime = "\u001b[38;5;241m{asctime:^9}\u001b[0m"
    message = "{message}"
    module = "\u001b[38;5;128m{module}\u001b[0m"
    FORMATS = {
        logging.DEBUG: f'{asctime} {module} \u001b[38;5;247m{levelname}: {message}\u001b[0m',
        logging.INFO: f"{asctime} {module} \u001b[38;5;75m{levelname}:\u001b[0m \u001b[38;5;252m{message}\u001b[0m",
        logging.WARNING: f"{asctime} {module} \u001b[38;5;220m{levelname}:\u001b[0m \u001b[38;5;230m{message}\u001b[0m",
        logging.ERROR: f"{asctime} {module} \u001b[38;5;160m{levelname}: {message}\u001b[0m",
        logging.CRITICAL: f"{asctime} {module} \u001b[38;5;196m{levelname}: {message}\u001b[0m",
    }
    
    class ColorFormatter(logging.Formatter):
        def format(self, record):
            log_format = FORMATS[record.levelno]
            formatter = logging.Formatter(log_format, style='{')
            return formatter.format(record)
    
    handler = logging.StreamHandler()
    handler.setFormatter(ColorFormatter())
    
    logging.basicConfig(
        level=logging.WARNING,
        handlers=[handler],
    )
    
    logging.getLogger('bot').setLevel(logging.DEBUG)
    
    logging.getLogger('discord').setLevel(logging.INFO)
    
    logging.getLogger('nordvpn').setLevel(logging.INFO)
