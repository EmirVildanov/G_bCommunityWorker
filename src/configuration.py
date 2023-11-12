# Vk API's interaction.
VK_CONFIG_PATH = "secrets/vkconfig.json"
COMMUNITY_ACCESS_TOKEN_KEY = "community_access_token"
SERVICE_TOKEN_KEY = "service_token"
GROUP_ID_KEY = "community_id"
VK_API_VERSION = "5.131"
APP_ID_KEY = "app_id"
SECURE_KEY_KEY = "secure_key"

# Server's interaction.
SERVER_CONFIG_PATH = "secrets/serverconfig.json"
SERVER_IP_KEY = "server_ip"
SERVER_PORT_KEY = "server_port"
SERVER_LOGIN_KEY = "server_login"

# MongoDB's interaction.
MONGODB_CONFIG_PATH = "secrets/mongoconfig.json"
MONGODB_CONFIG_LOGIN_KEY = "db_login"
MONGODB_CONFIG_PASSWORD_KEY = "db_password"

LOGGING_FILE_PATH = "secrets/logs.txt"

SAVING_ACTIVITY_INFO_REGEX = r"([01]) - ([0-2][0-9]:[0-6][0-9]) - ([1-7]+)"

DATETIME_WRITE_FORMAT = '%Y-%m-%d %H:%M:%S'

# Interval (period) with which we store the information about followers activity (whether they are online).
MINUTES_INTERVAL = 2
# The number of intervals of chosen length `MINUTES_INTERVAL` that fits into one day (e.g. in case the interval is
# equal to 2 minutes, there will be 720 such intervals).
MINUTES_INTERVALS_NUMBER = 24 * 60 // MINUTES_INTERVAL
