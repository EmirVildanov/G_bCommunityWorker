import json
import logging
import time
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

from re import search

from src.configuration import *
from src.db.mongo_worker import MongoWorker
from src.utils import Utils, CustomLoggingLevel
from src.vk.constants import SECRET_MESSAGE_LINE_ASKING_FOR_PASSWORD, SECRET_MESSAGE_LINE_ASKING_FOR_ACCOUNT_INFO, \
    SECRET_MESSAGE_LINE_ASKING_TO_CHANGE_PUBLIC_STATUS, CONNECTION_ERROR_TIMEOUT_WAIT_SECONDS, \
    CONNECTION_ERROR_RETRIES_THRESHOLD, CONNECTION_ERROR_RESET_SECONDS_TIME_SLEEP, \
    CONNECTION_ERROR_RESET_SECONDS_NEEDED, STARTUP_POSTS_READ_AMOUNT
from src.vk.model import PublicFollowerInfo, PrivateFollowerInfo, FollowerOnlineStatus, CommunityPost, \
    CommunityPostComment

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


class VkWorker:
    def __init__(self):
        """Function for bot initialization. Fields like `vk_session` are filled in here so that we don't have to
           define them later again in every function."""
        Utils.log("Bot started initialization")
        with open(VK_CONFIG_PATH, 'r') as vk_config:
            config_data = json.load(vk_config)
            community_access_token = config_data[COMMUNITY_ACCESS_TOKEN_KEY]
            service_token = config_data[SERVICE_TOKEN_KEY]
            group_id = config_data[GROUP_ID_KEY]

        # ================ VK API configuration ===============================
        self.group_id = int(group_id)
        # This api is used for interacting with community API as an admin through community access token.
        self.vk_community_session = vk_api.VkApi(token=community_access_token)
        self.vk_community_api = self.vk_community_session.get_api()
        # This api is used for interacting with community API as a random follower (e.g., when we need to access
        # community wall posts).
        self.vk_service_session = vk_api.VkApi(token=service_token)
        self.vk_service_api = self.vk_service_session.get_api()

        # ================ MongoDB configuration ===============================
        self.mongo_worker = MongoWorker()

        # ================ Worker util logic configuration ===============================
        # Counter of connection errors (e.g. appeared because of API timeout, bot not receiving any event).
        self.bot_connection_error_counter = 0
        self.seconds_past_after_last_connection_error = 0
        # Dirty workaround over impossibility to send message to user, who blocked messages from community.
        # We store a map of (user_if -> {(post_id, comment_id)}) so that we can reply them in comments.
        self.user_id_to_comment_ids_map = dict()

        Utils.log("Bot finished initialization")

    def get_owner_id(self):
        """Get id of group as owner."""
        # Note that this value must be negative (negative values correspond to community ids).
        return -self.group_id

    def requests_read_timeout_wrapper(self, function):
        """Function-workaround that ignores bot timeout.
           Bot timeout results from bot inactivity (not receiving messages from any user)."""
        while True:
            try:
                function()
            except requests.exceptions.ReadTimeout as e:
                Utils.log_error("Bot encountered read timeout. Resetting connection.", e)
                pass
            except requests.exceptions.ConnectionError as e:
                if self.bot_connection_error_counter > CONNECTION_ERROR_RETRIES_THRESHOLD:
                    Utils.log_error("Bot encountered connection error. Errors limit exceeded. Stopping bot.", e)
                    raise e
                Utils.log_error("Bot encountered connection error. Resetting connection.", e)
                self.seconds_past_after_last_connection_error = 0
                self.bot_connection_error_counter += 1
                time.sleep(CONNECTION_ERROR_TIMEOUT_WAIT_SECONDS)
                pass
            except Exception as e:
                message_string = str(type(e)) + str(e)
                Utils.log(message_string, CustomLoggingLevel.Error)
                raise e

    def connection_error_threshold_tracker(self):
        while True:
            if self.seconds_past_after_last_connection_error >= CONNECTION_ERROR_RESET_SECONDS_NEEDED:
                self.bot_connection_error_counter = 0
                self.seconds_past_after_last_connection_error = 0
            time.sleep(CONNECTION_ERROR_RESET_SECONDS_TIME_SLEEP)
            self.seconds_past_after_last_connection_error += CONNECTION_ERROR_RESET_SECONDS_TIME_SLEEP

    def fill_user_id_to_comment_ids_map(self):
        Utils.log("Bot started filling (user_id -> comment) map.")
        posts = self.get_community_posts(count=STARTUP_POSTS_READ_AMOUNT)
        for post in posts:
            post_id = post.id
            for comment in post.comments:
                comment_author_id = comment.from_id
                comment_id = comment.id
                post_comment_pair = (post_id, comment_id)
                if comment.from_id in self.user_id_to_comment_ids_map:
                    self.user_id_to_comment_ids_map[comment_author_id].add(post_comment_pair)
                else:
                    self.user_id_to_comment_ids_map[comment_author_id] = { post_comment_pair }
        Utils.log("Bot finished filling map.")


    def start_work(self):
        """Function that starts Bot for receiving and handling events."""
        self.fill_user_id_to_comment_ids_map()

        connection_errors_resetter_thread = threading.Thread(target=self.connection_error_threshold_tracker)
        connection_errors_resetter_thread.start()

        events_listener_thread = threading.Thread(target=self.requests_read_timeout_wrapper, args=[self.listen_events])
        events_listener_thread.start()

        Utils.log("Bot started working.")

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

    def get_community_post_comments(
            self,
            from_id: int,
            offset: int = 0,
            count: int = 100
    ) -> List[CommunityPostComment]:
        """Get concrete post comments."""
        Utils.log(f"Queried {count} post[{from_id}] comments with offset[{offset}].")

        owner_id = self.get_owner_id()
        posts_comments_info = self.vk_service_api.wall.getComments(
            owner_id=owner_id,
            post_id=from_id,
            offset=offset,
            count=count,
            v=VK_API_VERSION)[items_key]

        comments = []
        for comment_info in posts_comments_info:
            id = comment_info["id"]
            from_id = comment_info["from_id"]
            text = comment_info["text"]
            comment = CommunityPostComment(id, from_id, text)
            comments.append(comment)
        Utils.log(f"Query of {count} comments was executed.")
        return comments

    def get_community_posts(self, offset: int = 0, count: int = 100) -> List[CommunityPost]:
        """Get the community posts."""
        Utils.log(f"Queried {count} community posts with offset[{offset}].")
        owner_id = self.get_owner_id()
        community_posts_infos = self.vk_service_api.wall.get(
            owner_id=owner_id,
            offset=offset,
            count=count,
            v=VK_API_VERSION)[items_key]

        posts = []
        for post_info in community_posts_infos:
            post_id = post_info["id"]
            post_text = post_info["text"]

            comments = self.get_community_post_comments(post_id)

            post = CommunityPost(post_id, post_text, comments)
            posts.append(post)
        Utils.log(f"Query of {count} community posts was executed.")
        return posts

    def get_all_community_posts(self) -> List[CommunityPost]:
        """Using `get_community_posts` get all community posts."""
        all_posts = []
        current_res = []
        current_offset = 0
        step = 500
        while len(current_res) == 0:
            print("Query posts")
            current_res = self.get_community_posts(current_offset, step)
            all_posts.extend(current_res)
            current_offset += step
        return all_posts

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

    def reply_follower_message(self, follower_id: int, message: str) -> bool:
        """Helper function-wrapper over API for replying to followers messages.
           Returns True in case reply went successfully and False otherwise."""
        errors_prefix = f"Can't send reply[{message}] to follower[{follower_id}]. "

        try:
            self.vk_community_api.messages.send(
                user_id=follower_id,
                message=message,
                random_id=get_random_id(),
            )
            Utils.log(f"Bot replied to follower[{follower_id}] with [{message}].")
            return True
        except vk_api.exceptions.VkApiError as vk_api_e:
            if search("Can't send messages for users without permission", str(vk_api_e)):
                Utils.log_error(errors_prefix + "User restricted messages from community.", vk_api_e)
            else:
                Utils.log_error(errors_prefix + "Unknown VkApiError error.", vk_api_e)
        except Exception as e:
            Utils.log_error(errors_prefix + "Unknown error.", e)

        return False

    def reply_wall_post_comment(self, post_id: int, comment_id: int, message: str):
        """Helper function-wrapper over API for replying to post comments."""
        errors_prefix = f"Can't reply comment[{comment_id}] on post[{post_id}] wih message[{message}]. "

        try:
            self.vk_community_api.wall.createComment(
                owner_id=self.get_owner_id(),
                post_id=post_id,
                reply_to_comment=comment_id,
                message=message
            )
            Utils.log(f"Bot replied to comment[{comment_id}] on post[{post_id}] with message[{message}].")
        except vk_api.exceptions.VkApiError as vk_api_e:
            Utils.log_error(errors_prefix + "Unknown VkApiError error.", vk_api_e)
        except Exception as e:
            Utils.log_error(errors_prefix + "Unknown error.", e)

    def forced_reply_follower(self, follower_id: int, message: str):
        """Method executed when we aggressively want to send a message to user. Even if he/she blocked
        community messages."""
        # TODO: In case follower likes many posts he will spam in comments with our forced replies.
        #       Even in case he removes a like, he will born two comments that will stay as spam.
        #       Proposal:
        #       1)    Like -> span (add) comment.
        #       1.1)  Comment: ... + "Заранее спасибо! Я удалю комментарий, если ты уберёшь лайк",
        #             чтобы потом не приходилось плодить ещё один комментарий только ради "Спасибо!".
        #       2)    One more like -> delete previous comment and create one again (user will get new notification).
        #       3)    Like deleted -> delete comment.
        message_reply_result = self.reply_follower_message(follower_id, "Привет! " + message)
        if not message_reply_result:
            # For some reason we didn't succeed to reply user in private message.
            if follower_id in self.user_id_to_comment_ids_map:
                follower_set = self.user_id_to_comment_ids_map[follower_id]
                post_id, comment_id = list(follower_set)[0]
                self.reply_wall_post_comment(
                    post_id,
                    comment_id,
                    "Привет! Я не могу ответить тебе в личных сообщениях, поэтому напишу здесь: " + message
                )
            else:
                Utils.log(f"Can't forcefully reply[{message}] user[{follower_id}] in comments, because he is not in the map.")

    def handle_like_add(self, event):
        if event.object["object_type"] == "post":
            follower_id = event.object["liker_id"]
            added = self.mongo_worker.add_user_liked_post(follower_id, event.object["object_id"])
            if added:
                self.forced_reply_follower(
                    follower_id,
                    "В сообществе G_b действует экспериментальный безлайковый режим."
                    "Убери, пожалуйста, лайк с поста."
                )

    def handle_like_remove(self, event):
        if event.object["object_type"] == "post":
            follower_id = event.object["liker_id"]
            removed = self.mongo_worker.remove_user_liked_post(follower_id, event.object["object_id"])
            if removed:
                self.forced_reply_follower(
                    follower_id,
                    "Спасибо!"
                )

    def handle_message_new(self, event):
        return
        if event.from_chat:
            # Message came from shared community chat.
            return

            def reply_message(chat_id: int, message: str):
                """Some legacy logic (maybe specific for community shared chat)."""
                self.vk_community_api.messages.send(
                    # key=LONG_POLL_KEY,
                    # server=LONG_POLL_SERVER,
                    # ts=LONG_POLL_TS,
                    # This is a dirty hack that Vk developers ask us to do.
                    random_id=get_random_id(),
                    message=message,
                    chat_id=chat_id
                )

            follower_id = event.message["from_id"]
            text = event.message["text"]
            attachments = event.message["attachments"]
            follower_name = self.get_follower_info_by_id(follower_id).first_name

            if SECRET_MESSAGE_LINE_ASKING_FOR_PASSWORD in str(text):
                reply_message(event.chat_id,
                              f"{follower_name}, I can't give you your secret key here, "
                              f"cause it's a private info. \n"
                              f"Please write me in private community messages")
            elif len(attachments) == 1 and attachments[0]["type"] == "audio_message":
                reply_message(event.chat_id,
                              f"{follower_name}, anybody wants to listen to your stupid audio_message!")
            elif any_from_list_in_value(text, [*greetings, *russian_greetings]):
                reply_message(event.chat_id, f"Hello, {follower_name}!")
        elif event.to_me and event.from_user:
            # Message came from shared community chat.
            return
            message_sending_user_id = event.user_id
            message_sending_user_name = self.get_follower_info_by_id(message_sending_user_id)

            self.reply_follower_message(event.user_id, f"Hi! You are {message_sending_user_name}")
            if SECRET_MESSAGE_LINE_ASKING_FOR_PASSWORD in str(event.text):
                secret = self.mongo_worker.get_user_secret_key_by_id(event.user_id)
                reply_follower_message(event.user_id, f"Here's your password, {message_sending_user_name}: {secret}")
            elif SECRET_MESSAGE_LINE_ASKING_FOR_ACCOUNT_INFO in str(event.text):
                follower_id = event.user_id
                surname = self.mongo_worker.get_user_surname_by_id(follower_id)
                reply_follower_message(event.user_id,
                                       f"Here's your account info:\nId: {follower_id}\nSurname: {surname}")
            elif SECRET_MESSAGE_LINE_ASKING_TO_CHANGE_PUBLIC_STATUS in str(event.text):
                follower_id = event.user_id
                new_publicity_status = self.mongo_worker.change_follower_publicity_status(follower_id)
                reply_follower_message(event.user_id,
                                       f"Your account publicity status changed to {new_publicity_status}")
            elif any_from_list_in_value(event.text, [*greetings, *russian_greetings]):
                reply_follower_message(event.user_id, f"Hi, {message_sending_user_name}! :)")
            else:
                reply_follower_message(event.user_id,
                                       f"I'm sorry, {message_sending_user_name}. I don't understand such command yet")
                self.mongo_worker.insert_bot_message(BotMessageInfo(event.user_id, event.text))

    def handle_wall_reply_new(self, event):
        """Logic of handling new comments appearance."""
        event_object = event.object
        comment_id = event_object["id"]
        post_id = event_object["post_id"]
        from_id = event_object["from_id"]

        post_comment_pair = (post_id, comment_id)

        if from_id in self.user_id_to_comment_ids_map:
            self.user_id_to_comment_ids_map[from_id].add(post_comment_pair)
        else:
            self.user_id_to_comment_ids_map[from_id] = { post_comment_pair }

    def handle_wall_reply_delete(self, event):
        """Logic of handling comments deletion."""
        event_object = event.object
        comment_id = event_object["id"]
        deleter_id = event_object["deleter_id"]
        post_id = event_object["post_id"]

        post_comment_pair = (post_id, comment_id)

        if deleter_id in self.user_id_to_comment_ids_map:
            deleter_set = self.user_id_to_comment_ids_map[deleter_id]
            if post_comment_pair in deleter_set:
                self.user_id_to_comment_ids_map[deleter_id].remove(post_comment_pair)

    def listen_events(self):
        """Process all events coming from VK server."""
        # TODO: Currently if we take an event from longpoll queue, but fail to handle it (e.g. when Exception is raised),
        #       we miss the event. I propose to add such events in a queue (e.g. RabbitMQ or Redis) and send an
        #       acknowledge message only in case of successful logic execution.
        longpoll = VkBotLongPoll(self.vk_community_session, self.group_id)
        Utils.log("Started listening events")
        for event in longpoll.listen():
            Utils.log(f"Event appeared: {event}")
            if event.type == "like_add":
                self.handle_like_add(event)
            elif event.type == "like_remove":
                self.handle_like_remove(event)
            elif event.type == VkBotEventType.MESSAGE_NEW:
                self.handle_message_new(event)
            elif event.type == VkBotEventType.WALL_REPLY_NEW:
                self.handle_wall_reply_new(event)
            elif event.type == VkBotEventType.WALL_REPLY_DELETE:
                self.handle_wall_reply_delete(event)
