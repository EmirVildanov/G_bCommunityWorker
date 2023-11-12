import json
from dataclasses import dataclass
from typing import List

import datetime
import requests
import vk_api
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
from vk_api.keyboard import VkKeyboard, VkKeyboardColor
from vk_api.longpoll import VkLongPoll, VkEventType
from vk_api.utils import get_random_id
import threading

from src.configuration import *
from src.db.mongo_worker import MongoWorker
from src.utils import Utils
from src.vk.constants import SECRET_MESSAGE_LINE_ASKING_FOR_PASSWORD, SECRET_MESSAGE_LINE_ASKING_FOR_ACCOUNT_INFO, \
    SECRET_MESSAGE_LINE_ASKING_TO_CHANGE_PUBLIC_STATUS
from src.vk.model import PublicFollowerInfo, PrivateFollowerInfo, FollowerOnlineStatus, CommunityPost

# Constants for recognizing followers messages.
greetings = ['hi', 'hello', 'welcome', 'good morning', 'good afternoon', 'good evening']
russian_greetings = ['прив', 'даров', 'добрый день', 'добрый вечер', 'добрая ночь', 'хай']

# Constants for accessing fields from Vk API responses.
id_key = "id"
first_name_key = "first_name"
last_name_key = "last_name"
items_key = "items"
last_seen_key = "last_seen"
platform_key = "platform"
online_key = "online"
time_key = "time"


def any_from_list_in_value(value, words_list) -> bool:
    """Checks whether some element from `words_list` fully contained in the `value`.
       E.g. used to check that some keyword is contained in the follower's message."""
    for item in words_list:
        if item in str(value).lower():
            return True
    return False


def bot_timeout_wrapper(function):
    """Function-workaround that ignores bot timeout.
       Bot timeout results from bot inactivity (not receiving messages from any user).
       TODO: we need to replace generic Exception with more specific TimeoutExcpection"""
    while True:
        try:
            function()
        except requests.exceptions.ReadTimeout:
            Utils.log_info("Bot encountered read timeout. Moving on.")
            pass


class VkBot:
    def __init__(self):
        """Function for bot initialization. Fields like `vk_session` are filled in here so that we don't have to
           define them later again in every function."""
        Utils.log_info("Bot started initialization")
        with open(VK_CONFIG_PATH, 'r') as vk_config:
            config_data = json.load(vk_config)
            community_access_token = config_data[COMMUNITY_ACCESS_TOKEN_KEY]
            service_token = config_data[SERVICE_TOKEN_KEY]
            group_id = config_data[GROUP_ID_KEY]

        self.group_id = group_id

        # This api is used for interacting with community API as an admin through community access token.
        self.vk_community_session = vk_api.VkApi(token=community_access_token)
        self.vk_community_api = self.vk_community_session.get_api()
        # This api is used for interacting with community API as a random follower (e.g., when we need to access
        # community wall posts).
        self.vk_service_session = vk_api.VkApi(token=service_token)
        self.vk_service_api = self.vk_service_session.get_api()

        self.mongo_worker = MongoWorker()

        Utils.log_info("Bot finished initialization")

    def start_work(
            self,
            listen_private_messages=False,
            listen_public_messages=False,
            listen_events=False
    ):
        """Function that starts Bot for receiving and handling events."""
        Utils.log_info("Bot started working")
        if listen_public_messages:
            public_messages_thread = threading.Thread(target=bot_timeout_wrapper, args=[self.listen_public_messages])
            public_messages_thread.start()

        if listen_private_messages:
            private_messages_thread = threading.Thread(target=bot_timeout_wrapper, args=[self.listen_private_messages])
            private_messages_thread.start()

        if listen_events:
            events_thread = threading.Thread(target=bot_timeout_wrapper, args=[self.listen_events])
            events_thread.start()

        Utils.log_info("Bot successfully started all needed threads.")

    def get_long_poll_server_info(self):
        """Get information about long poll server (key, server, ts)."""
        return self.vk_community_api.groups.getLongPollServer(group_id=self.group_id, v=VK_API_VERSION)

    def get_follower_info_by_id(self, follower_id) -> PublicFollowerInfo:
        """Get information about concrete follower."""
        follower_info = self.vk_community_api.users.get(user_id=follower_id, v=VK_API_VERSION)[0]
        first_name, last_name = follower_info[first_name_key], follower_info[last_name_key]
        return PublicFollowerInfo(follower_id, first_name, last_name)

    def get_all_followers_info(self) -> List[PublicFollowerInfo]:
        """Get information about all community followers"""
        follower_ids = self.vk_community_api.groups.getMembers(group_id=self.group_id, v=VK_API_VERSION)[items_key]
        print(f"Followers ids: {follower_ids}")
        followers_info = self.vk_community_api.users.get(user_ids=follower_ids, v=VK_API_VERSION)
        followers_info_formatted = []
        print(f"Followers info: {followers_info}")
        for follower_info in followers_info:
            print(f"Follower info unforamtted: {follower_info}")
            follower_id, first_name, last_name = follower_info[id_key], follower_info[first_name_key], follower_info[
                last_name_key]
            followers_info_formatted.append(PublicFollowerInfo(follower_id, first_name, last_name))
        return followers_info_formatted

    def get_community_posts(self, offset: int = 0, count: int = 100) -> List[CommunityPost]:
        """Get all the community posts."""
        # Note that this value must be negative (negative values correspond to community ids).
        owner_id = -self.group_id
        community_posts_info = \
            self.vk_service_api.wall.get(owner_id=owner_id, offset=offset, count=count, v=VK_API_VERSION)[items_key]
        for post_info in community_posts_info:
            print(f"Post info: {post_info}")
        posts = []
        for post_info in community_posts_info:
            post_text = post_info["text"]
            post = CommunityPost(post_text)
            posts.append(post)
        return posts

    def get_followers_current_online_status(self, followers_info: List[PublicFollowerInfo]):
        """Get information about all the followers indicating whether they are currently online or not. In case they are
           online, get the information about which platform they use Vk from."""
        current_datetime = Utils.get_date_truncated_by_minutes(datetime.datetime.now())

        follower_online_statuses = []
        follower_ids = [follower_info.id for follower_info in followers_info]
        follower_infos = self.vk_community_api.users.get(user_ids=follower_ids, fields=f"{online_key},{last_seen_key}",
                                                         v=VK_API_VERSION)

        # Calculate the interval (time X-axis mark) in which we should store activity information.
        current_minutes_interval = (
                                           current_datetime.time().hour * 60 + current_datetime.time().minute) // MINUTES_INTERVAL

        for follower_info in follower_infos:
            follower_id = follower_info[id_key]
            online = follower_info[online_key]
            if last_seen_key in follower_info:
                last_seen_info = follower_info[last_seen_key]
                last_seen_time, platform = int(last_seen_info[time_key]), int(last_seen_info[platform_key])

                # `utcfromtimestamp` converts long number (in which Vk represents time) into datetime format
                last_seen_time_datetime = (
                    datetime.datetime.utcfromtimestamp(last_seen_time))
            else:
                last_seen_time_datetime, platform = None, None

            follower_online_statuses.append(
                FollowerOnlineStatus(
                    follower_id,
                    current_minutes_interval,
                    current_datetime,
                    online,
                    last_seen_time_datetime,
                    platform)
            )
        return follower_online_statuses

    def reply_follower_message(self, follower_id: int, message: str):
        """Helper function-wrapper over API for replying to followers messages."""
        Utils.log_info(f"Bot replied to {follower_id} with [{message}]")
        self.vk_community_api.messages.send(
            user_id=follower_id,
            message=message,
            random_id=get_random_id(),
        )

    def listen_private_messages(self):
        """Process messages sent to private chat between community and concrete follower."""
        longpoll = VkLongPoll(self.vk_community_session)

        Utils.log_info("Bot started listening private messages")
        for event in longpoll.listen():
            if event.type == VkEventType.MESSAGE_NEW and event.to_me and event.from_user:
                message_sending_user_id = event.user_id
                message_sending_user_name = self.get_follower_info_by_id(message_sending_user_id)

                self.reply_follower_message(event.user_id,
                                            f"Hi! You are {message_sending_user_name}")
        #         if SECRET_MESSAGE_LINE_ASKING_FOR_PASSWORD in str(event.text):
        #             secret = self.mongo_worker.get_user_secret_key_by_id(event.user_id)
        #             reply_follower_message(event.user_id, f"Here's your password, {message_sending_user_name}: {secret}")
        #         elif SECRET_MESSAGE_LINE_ASKING_FOR_ACCOUNT_INFO in str(event.text):
        #             follower_id = event.user_id
        #             surname = self.mongo_worker.get_user_surname_by_id(follower_id)
        #             reply_follower_message(event.user_id, f"Here's your account info:\nId: {follower_id}\nSurname: {surname}")
        #         elif SECRET_MESSAGE_LINE_ASKING_TO_CHANGE_PUBLIC_STATUS in str(event.text):
        #             follower_id = event.user_id
        #             new_publicity_status = self.mongo_worker.change_follower_publicity_status(follower_id)
        #             reply_follower_message(event.user_id, f"Your account publicity status changed to {new_publicity_status}")
        #         elif any_from_list_in_value(event.text, [*greetings, *russian_greetings]):
        #             reply_follower_message(event.user_id, f"Hi, {message_sending_user_name}! :)")
        #         else:
        #             reply_follower_message(event.user_id,
        #                           f"I'm sorry, {message_sending_user_name}. I don't understand such command yet")
        #             self.mongo_worker.insert_bot_message(BotMessageInfo(event.user_id, event.text))

    def listen_public_messages(self):
        """Process messages sent to public chat between community and any follower that entered the public chat."""
        return
        # public_longpoll = VkBotLongPoll(self.vk_session, MY_GROUP_ID)
        # public_vk = self.vk_session.get_api()
        #
        # def reply_message(chat_id: int, message: str):
        #     public_vk.messages.send(
        #         key=LONG_POLL_KEY,
        #         server=LONG_POLL_SERVER,
        #         ts=LONG_POLL_TS,
        #         # This is a dirty hack that Vk developers ask us to to (API ).
        #         random_id=get_random_id(),
        #         message=message,
        #         chat_id=chat_id
        #     )
        #
        # Utils.log_info("Started listening public messages")
        # for event in public_longpoll.listen():
        #     if event.type == VkBotEventType.MESSAGE_NEW and event.from_chat:
        #         print(event.message)
        #         follower_id = event.message["from_id"]
        #         text = event.message["text"]
        #         attachments = event.message["attachments"]
        #         follower_name = self.vk_worker.get_follower_info_by_id(follower_id).name
        #
        #         if SECRET_MESSAGE_LINE_ASKING_FOR_PASSWORD in str(text):
        #             reply_message(event.chat_id,
        #                           f"{follower_name}, I can't give you your secret key here, "
        #                           f"cause it's a private info. \n"
        #                           f"Please write me in private community messages")
        #         elif len(attachments) == 1 and attachments[0]["type"] == "audio_message":
        #             reply_message(event.chat_id,
        #                           f"{follower_name}, anybody wants to listen to your stupid audio_message!")
        #         elif any_from_list_in_value(text, [*greetings, *russian_greetings]):
        #             reply_message(event.chat_id, f"Hello, {follower_name}!")

    def listen_events(self):
        """Process such events as likes, ..."""
        longpoll = VkBotLongPoll(self.vk_community_session, self.group_id)
        Utils.log_info("Started listening events")
        for event in longpoll.listen():
            Utils.log_info(f"Event appeared: {event}")
            if event.type == "like_add":
                follower_id = event.object["liker_id"]
                added = self.mongo_worker.add_user_liked_post(follower_id, event.object["object_id"])
                if added:
                    self.reply_follower_message(follower_id, "Привет! В сообществе G_b действует экспериментальный безлайковый режим. Убери, пожалуйста, лайк с поста.")

            elif event.type == "like_remove":
                follower_id = event.object["liker_id"]
                removed = self.mongo_worker.remove_user_liked_post(follower_id, event.object["object_id"])
                if removed:
                    self.reply_follower_message(follower_id, "Спасибо!")
