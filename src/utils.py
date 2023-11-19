import datetime
from enum import Enum

import requests
import logging

from src.configuration import LOGGING_FILE_PATH

class CustomLoggingLevel(Enum):
    Info = 1
    Error = 2



class Utils:

    @staticmethod
    def init():
        return
        # logging.basicConfig(filename=LOGGING_FILE_PATH, level=logging.DEBUG)

    @staticmethod
    def get_date_truncated_by_minutes(date: datetime) -> datetime:
        return datetime.datetime(date.year, date.month, date.day, date.hour, date.minute)

    @staticmethod
    def get_date_truncated_by_day(date: datetime) -> datetime:
        return datetime.datetime(date.year, date.month, date.day)

    @staticmethod
    def get_date_truncated_from_string(date_string: str, format: str) -> datetime.datetime:
        return Utils.get_date_truncated_by_day(Utils.get_datetime_from_string(date_string, format))

    @staticmethod
    def get_datetime_from_string(date_string: str, format: str) -> datetime.datetime:
        return datetime.datetime.strptime(date_string, format)

    @staticmethod
    def log(info, level=CustomLoggingLevel.Info):
        info_message = ""
        if level == CustomLoggingLevel.Info:
            info_message += "INFO: "
        elif level == CustomLoggingLevel.Error:
            info_message += "ERROR: "
        info_message += f"""{datetime.datetime.now().strftime("[%m/%d/%Y@%H:%M:%S]")} {info}"""
        print(info_message)
        with open(LOGGING_FILE_PATH, 'a') as f:
            file_info_message = info_message + "\n"
            f.write(file_info_message)

    @staticmethod
    def log_error(info_message: str, error: Exception):
        message_string = info_message + " [" + str(type(error)) + ": " + str(error) + "]."
        Utils.log(message_string, CustomLoggingLevel.Error)



    @staticmethod
    def count_words_at_url(url):
        resp = requests.get(url)
        return len(resp.text.split())
