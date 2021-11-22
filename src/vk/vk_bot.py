import vk_api
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
from vk_api.keyboard import VkKeyboard, VkKeyboardColor
from vk_api.longpoll import VkLongPoll, VkEventType
from vk_api.utils import get_random_id
import threading

from src.configuration import *
from src.mongo.mongo_worker import MongoWorker
from src.utils import Utils
from src.vk.constants import SECRET_MESSAGE_LINE_ASKING_FOR_PASSWORD, SECRET_MESSAGE_LINE_ASKING_FOR_ACCOUNT_INFO, \
    SECRET_MESSAGE_LINE_ASKING_TO_CHANGE_PUBLIC_STATUS
from src.vk.vk_worker import VkWorker, BotMessageInfo

greetings = ['hi', 'hello', 'welcome', 'good morning', 'good afternoon', 'good evening']
russian_greetings = ['прив', 'дарова', 'добрый день', 'добрый вечер', 'добрая ночь', 'хай']


def any_from_list_in_value(value, words_list) -> bool:
    for item in words_list:
        if item in str(value).lower():
            return True
    return False


def get_keyboard():
    keyboard = VkKeyboard(one_time=True)
    keyboard.add_button('Hi, G_b!', color=VkKeyboardColor.PRIMARY)
    keyboard.add_button('Goodbye, G_b!', color=VkKeyboardColor.PRIMARY)
    return keyboard


class VkBot:
    def __init__(self):
        self.vk_worker = VkWorker(GROUP_ACCESS_TOKEN)
        self.mongo_worker = MongoWorker()
        self.vk_session = vk_api.VkApi(token=GROUP_ACCESS_TOKEN)

    def start_work(self):
        public_thread = threading.Thread(target=self.bot_timeout_cover, args=[self.listen_public_messages])
        public_thread.start()

        private_thread = threading.Thread(target=self.bot_timeout_cover, args=[self.listen_private_messages])
        private_thread.start()

    def bot_timeout_cover(self, function):
        while True:
            try:
                function()
            except Exception:
                pass

    # process messages sent to private group-user chat
    def listen_private_messages(self):
        Utils.log_info("Started listening private messages")
        private_longpoll = VkLongPoll(self.vk_session)
        private_vk = self.vk_session.get_api()

        def reply_message(user_id: int, message: str):
            private_vk.messages.send(
                user_id=user_id,
                message=message,
                random_id=get_random_id(),
            )

        for event in private_longpoll.listen():
            if event.type == VkEventType.MESSAGE_NEW and event.to_me and event.from_user:
                message_sending_user_id = event.user_id
                message_sending_user_name = self.vk_worker.get_follower_info_by_id(message_sending_user_id).name

                if SECRET_MESSAGE_LINE_ASKING_FOR_PASSWORD in str(event.text):
                    secret = self.mongo_worker.get_user_secret_key_by_id(event.user_id)
                    reply_message(event.user_id, f"Here's your password, {message_sending_user_name}: {secret}")
                elif SECRET_MESSAGE_LINE_ASKING_FOR_ACCOUNT_INFO in str(event.text):
                    follower_id = event.user_id
                    surname = self.mongo_worker.get_user_surname_by_id(follower_id)
                    reply_message(event.user_id, f"Here's your account info:\nId: {follower_id}\nSurname: {surname}")
                elif SECRET_MESSAGE_LINE_ASKING_TO_CHANGE_PUBLIC_STATUS in str(event.text):
                    follower_id = event.user_id
                    new_publicity_status = self.mongo_worker.change_follower_publicity_status(follower_id)
                    reply_message(event.user_id, f"Your account publicity status changed to {new_publicity_status}")
                elif any_from_list_in_value(event.text, [*greetings, *russian_greetings]):
                    reply_message(event.user_id, f"Hi, {message_sending_user_name}! :)")
                else:
                    reply_message(event.user_id,
                                  f"I'm sorry, {message_sending_user_name}. I don't understand such command yet")
                    self.mongo_worker.insert_bot_message(BotMessageInfo(event.user_id, event.text))

    # process messages sent to public group-users chat
    def listen_public_messages(self):
        Utils.log_info("Started listening public messages")
        public_longpoll = VkBotLongPoll(self.vk_session, MY_GROUP_ID)
        public_vk = self.vk_session.get_api()

        def reply_message(chat_id: int, message: str):
            public_vk.messages.send(
                key=LONG_POLL_KEY,
                server=LONG_POLL_SERVER,
                ts=LONG_POLL_TS,
                random_id=get_random_id(),
                message=message,
                chat_id=chat_id
            )

        for event in public_longpoll.listen():
            if event.type == VkBotEventType.MESSAGE_NEW and event.from_chat:
                print(event.message)
                follower_id = event.message["from_id"]
                text = event.message["text"]
                attachments = event.message["attachments"]
                follower_name = self.vk_worker.get_follower_info_by_id(follower_id).name

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
