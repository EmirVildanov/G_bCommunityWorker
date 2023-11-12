import datetime
import json
import os
from typing import List, Optional

import pymongo

from src.configuration import MONGODB_CONFIG_LOGIN_KEY, MONGODB_CONFIG_PATH, SERVER_CONFIG_PATH, SERVER_IP_KEY, \
    SERVER_PORT_KEY, MONGODB_CONFIG_PASSWORD_KEY
from src.utils import Utils
from src.db.constants import *
from src.vk.model import PrivateFollowerInfo, PublicFollowerInfo, BotMessage


class MongoWorker:
    def __init__(self):
        with open(SERVER_CONFIG_PATH) as server_config:
            server_data = json.load(server_config)
            server_ip = server_data[SERVER_IP_KEY]
            server_port = server_data[SERVER_PORT_KEY]
        with open(MONGODB_CONFIG_PATH) as mongo_config:
            config_data = json.load(mongo_config)
            mongodb_login = config_data[MONGODB_CONFIG_LOGIN_KEY]
            mongodb_password = config_data[MONGODB_CONFIG_PASSWORD_KEY]

        connection_url = f"mongodb://{mongodb_login}:{mongodb_password}@{server_ip}:{server_port}/"
        self.client = pymongo.MongoClient(connection_url)
        self.db = self.client.gb

        # Collections:
        self.likes = self.db.likes
        # self.accounts = self.db.accounts
        # self.activity_data = self.db.activity_data
        # self.bot_messages = self.db.bot_messages

    def add_user_liked_post(self, follower_id: int, post_id: int) -> bool:
        result = list(self.likes.find({ID_KEY : follower_id}))
        if len(result) == 0:
            new_document = {
                ID_KEY: follower_id,
                POST_OBJECT_ID_KEY: [post_id]
            }
            self.likes.insert_one(new_document)
            return True
        else:
            result = self.likes.update_one(
                { ID_KEY: follower_id },
                { "$push": {POST_OBJECT_ID_KEY: post_id} }
            )
            if result.matched_count == 0 or result.modified_count == 0:
                return False
            else:
                return True

    def remove_user_liked_post(self, follower_id: int, post_id: int) -> bool:
        result = list(self.likes.find({ID_KEY: follower_id, POST_OBJECT_ID_KEY: post_id}))
        if len(result) == 0:
            return False
        else:
            result = self.likes.update_one(
                {ID_KEY: follower_id},
                {"$pull": {POST_OBJECT_ID_KEY: post_id}}
            )
            if result.matched_count == 0 or result.modified_count == 0:
                return False
            else:
                return True
    def get_user_secret_key_by_id(self, follower_id: int) -> Optional[str]:
        """Get u"""
        result = self.accounts.find_one({ID_KEY: follower_id})
        if result is not None:
            return result[SECRET_KEY_KEY]
        return None

    def get_user_surname_by_id(self, follower_id: int):
        result = self.accounts.find_one({ID_KEY: follower_id})
        if result is not None:
            return result[LAST_NAME_KEY]
        return None

    def insert_followers_info(self, followers_info: List[PrivateFollowerInfo]):
        already_existed_accounts = list(self.accounts.find())
        already_existed_ids = [item["id"] for item in already_existed_accounts]
        for follower_info in followers_info:
            if follower_info.id not in already_existed_ids:
                follower_document = {
                    ID_KEY: follower_info.id,
                    FIRST_NAME_KEY: follower_info.first_name,
                    LAST_NAME_KEY: follower_info.last_name,
                    SECRET_KEY_KEY: self.vk_worker.generate_follower_secret_key(follower_info),
                    IS_PUBLIC_KEY: False
                }
                self.accounts.insert_one(follower_document)
                Utils.log_info(f"Inserted {follower_info.first_name} {follower_info.last_name} into accounts collection")

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
                if date.second_i != 0 or date.microsecond != 0:
                    print(date)

        check()

    def insert_activity_info(self, followers_info: List[PublicFollowerInfo]):
        activities_info = self.vk_worker.get_followers_current_online_status(followers_info)

        for activity_info in activities_info:
            activity_document = {
                ID_KEY: activity_info.follower_id,
                MINUTES_INTERVAL_NUMBER_KEY: activity_info.minutes_interval_number,
                DATETIME_KEY: activity_info.datetime,
                LAST_SEEN_DATETIME_KEY: activity_info.last_seen_datetime,
                ONLINE_KEY: activity_info.online,
                PLATFORM_KEY: activity_info.platform
            }
            self.activity_data.insert_one(activity_document)
        Utils.log_info(f"Inserted activities info")

    def insert_bot_message(self, bot_message_info: BotMessage):
        bot_message_document = {
            ID_KEY: bot_message_info.id,
            TEXT_KEY: bot_message_info.text
        }
        self.bot_messages.insert_one(bot_message_document)

    def made_interval_activity_filling_action(self):
        followers_info = self.vk_worker.get_all_followers_info()
        self.prepare_accounts_collection(followers_info)
        self.insert_activity_info(followers_info)
