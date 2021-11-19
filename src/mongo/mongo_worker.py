import datetime
import os
from typing import List

import pymongo

from src.configuration import GROUP_ACCESS_TOKEN
from src.utils import Utils
from src.vk.vk_worker import VkWorker, FollowerInfo, BotMessageInfo, PrivateFollowerInfo
from src.mongo.constants import *


class MongoWorker:
    def __init__(self):
        self.vk_worker = VkWorker(GROUP_ACCESS_TOKEN)

        mongodb_login = os.environ.get(MONGODB_USERNAME_KEY, None)
        if mongodb_login is None:
            raise RuntimeError(f"Can't read environment MONGODB_USERNAME_KEY variable")
        mongodb_password = os.environ.get(MONGODB_PASSWORD_KEY, None)
        if mongodb_password is None:
            raise RuntimeError("Can't read environment MONGODB_PASSWORD variable")

        connection_url = f"mongodb+srv://{mongodb_login}:{mongodb_password}@cluster0.bhjda.mongodb.net/Cluster0?retryWrites=true&w=majority"
        self.client = pymongo.MongoClient(connection_url)
        self.db = self.client.activity_tracker
        self.accounts = self.db.accounts
        self.activity_data = self.db.activity_data
        self.bot_messages = self.db.bot_messages

    # Returns None if there is no account with such id
    def get_user_secret_key_by_id(self, follower_id: int):
        result = self.accounts.find_one({ID_KEY: follower_id})
        if result is not None:
            return result[SECRET_KEY_KEY]
        return None

    def get_user_surname_by_id(self, follower_id: int):
        result = self.accounts.find_one({ID_KEY: follower_id})
        if result is not None:
            return result[SURNAME_KEY]
        return None

    def insert_followers_info(self, followers_info: List[PrivateFollowerInfo]):
        already_existed_accounts = list(self.accounts.find())
        already_existed_ids = [item["id"] for item in already_existed_accounts]
        for follower_info in followers_info:
            if follower_info.id not in already_existed_ids:
                follower_document = {
                    ID_KEY: follower_info.id,
                    NAME_KEY: follower_info.name,
                    SURNAME_KEY: follower_info.surname,
                    SECRET_KEY_KEY: self.vk_worker.generate_follower_secret_key(follower_info),
                    IS_PUBLIC_KEY: False
                }
                self.accounts.insert_one(follower_document)
                Utils.log_info(f"Inserted {follower_info.name} {follower_info.surname} into accounts collection")

    def change_follower_publicity_status(self, follower_id: int) -> bool:
        account = self.accounts.find_one({ID_KEY: follower_id})
        old_publicity_status = account[IS_PUBLIC_KEY]
        new_publicity_status = not old_publicity_status
        self.accounts.update_one(
            {ID_KEY: account[ID_KEY]},
            {"$set": {IS_PUBLIC_KEY: new_publicity_status},
             "$currentDate": {"lastModified": True}}
        )
        return new_publicity_status

    def prepare_accounts_collection(self, followers_info: List[PrivateFollowerInfo]):
        self.insert_followers_info(followers_info)
        Utils.log_info("Prepared followers info")

    def fix_followers_collection(self):
        accounts = self.accounts.find()
        for account in accounts:
            self.accounts.update_one(
                {ID_KEY: account[ID_KEY]},
                {"$set": {IS_PUBLIC_KEY: False},
                 "$currentDate": {"lastModified": True}}
            )

    def fix_activity_collection(self):
        activity_data = self.activity_data.find()

        def update_datetime():
            unique_dates = [activity[DATETIME_KEY] for activity in activity_data]
            unique_dates = sorted(list(set(unique_dates)))
            for date in unique_dates:
                updated_date = Utils.get_date_truncated_by_minutes(date)
                self.activity_data.update_many(
                    {DATETIME_KEY: date},
                    {"$set": {DATETIME_KEY: updated_date},
                     "$currentDate": {"lastModified": True}}
                )
                print(f"Updated {date}")

        def update_last_seen_datetime():
            self.activity_data.update_many(
                {},
                {"$set": {LAST_SEEN_DATETIME_KEY: None},
                 "$currentDate": {"lastModified": True}}
            )

        def check():
            for activity in activity_data:
                date = activity[DATETIME_KEY]
                if date.second != 0 or date.microsecond != 0:
                    print(date)

        check()

    def insert_activity_info(self, followers_info: List[FollowerInfo]):
        current_date = Utils.get_date_truncated_by_minutes(datetime.datetime.now())
        activities_info = self.vk_worker.get_followers_activity_info(current_date, followers_info)

        for activity_info in activities_info:
            activity_document = {
                ID_KEY: activity_info.id,
                MINUTES_INTERVAL_NUMBER_KEY: activity_info.minutes_interval_number,
                DATETIME_KEY: activity_info.datetime,
                LAST_SEEN_DATETIME_KEY: activity_info.last_seen_datetime,
                ONLINE_KEY: activity_info.online,
                PLATFORM_KEY: activity_info.platform
            }
            self.activity_data.insert_one(activity_document)
        Utils.log_info(f"Inserted activities info")

    def insert_bot_message(self, bot_message_info: BotMessageInfo):
        bot_message_document = {
            ID_KEY: bot_message_info.id,
            TEXT_KEY: bot_message_info.text
        }
        self.bot_messages.insert_one(bot_message_document)

    def made_interval_activity_filling_action(self):
        followers_info = self.vk_worker.get_followers_info()
        self.prepare_accounts_collection(followers_info)
        self.insert_activity_info(followers_info)
