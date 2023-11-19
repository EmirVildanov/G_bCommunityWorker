# Bot communication.
SECRET_MESSAGE_LINE_ASKING_FOR_PASSWORD = "Please, give me a password to show my activity info."
SECRET_MESSAGE_LINE_ASKING_FOR_ACCOUNT_INFO = "Please, give me my account info."
SECRET_MESSAGE_LINE_ASKING_TO_CHANGE_PUBLIC_STATUS = "Please, change my account publicity status."

# Worker configuration.
# * In case we get `requests.error.ConnectionError` (e.g., because bot API timeout encountered as no events appeared
#   in some time) we will wait this time before reconnecting.
CONNECTION_ERROR_TIMEOUT_WAIT_SECONDS = 5
# * In case bot encounters `requests.error.ConnectionError` too often (in a short period of time) without stable work,
#   it means smth is going wrong. We don't want to restart it (reconnect to server) as soon as it won't do any good. So we stop it.
CONNECTION_ERROR_RETRIES_THRESHOLD = 3
# * If bot stably works without encountering any connection error we can reset out error counter to 0.
CONNECTION_ERROR_RESET_SECONDS_NEEDED = 120
# * Time we sleep in an endless loop before checking whether we need to reset errors counter.
CONNECTION_ERROR_RESET_SECONDS_TIME_SLEEP = 10

# Dirty hack over impossibility to send messages to users.
# * Amount of posts scanned from the top of community in order to build (user_id -> comment_id) map.
#   As soon as we can't send private message, we respond users in comments.
STARTUP_POSTS_READ_AMOUNT = 10
