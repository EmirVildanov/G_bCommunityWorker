import os

APP_ACCESS_TOKEN_KEY = "APP_ACCESS_TOKEN"
APP_ACCESS_TOKEN = os.getenv(APP_ACCESS_TOKEN_KEY, None)
if APP_ACCESS_TOKEN is None:
    raise RuntimeError(f"Can't read environment APP_ACCESS_TOKEN_KEY variable")

GROUP_ACCESS_TOKEN_KEY = "GROUP_ACCESS_TOKEN"
GROUP_ACCESS_TOKEN = os.getenv(GROUP_ACCESS_TOKEN_KEY, None)
if GROUP_ACCESS_TOKEN is None:
    raise RuntimeError(f"Can't read environment GROUP_ACCESS_TOKEN_KEY variable")

LONG_POLL_KEY_KEY = "LONG_POLL_KEY"
LONG_POLL_KEY = os.getenv(GROUP_ACCESS_TOKEN_KEY, None)
if LONG_POLL_KEY is None:
    raise RuntimeError(f"Can't read environment LONG_POLL_KEY_KEY variable")

LONG_POLL_SERVER = 'https://lp.vk.com/wh162927036'
LONG_POLL_TS = '1'

MY_GROUP_ID = 162927036
VK_API_VERSION = "5.131"

SAVING_ACTIVITY_INFO_REGEX = r"([01]) - ([0-2][0-9]:[0-6][0-9]) - ([1-7]+)"

DATETIME_WRITE_FORMAT = '%Y-%m-%d %H:%M:%S'

MINUTES_INTERVAL = 2
MINUTES_INTERVALS_NUMBER = 24 * 60 // MINUTES_INTERVAL
