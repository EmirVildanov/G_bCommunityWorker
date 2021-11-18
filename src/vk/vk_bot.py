import vk_api
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
from vk_api.keyboard import VkKeyboard, VkKeyboardColor
from vk_api.longpoll import VkLongPoll, VkEventType
from vk_api.utils import get_random_id
import threading

from src.configuration import *
from src.mongo.mongo_worker import MongoWorker
from src.utils import Utils
from src.vk.vk_worker import VkWorker

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
        public_thread = threading.Thread(target=self.listen_public_messages)
        public_thread.start()

        private_thread = threading.Thread(target=self.listen_private_messages)
        private_thread.start()

    # process messages sent to private group-user chat
    def listen_private_messages(self):
        Utils.log_info("Started listening private messages")
        private_longpoll = VkLongPoll(self.vk_session)
        private_vk = self.vk_session.get_api()

        for event in private_longpoll.listen():
            if event.type == VkEventType.MESSAGE_NEW and event.to_me and event.from_user:
                message_sending_user_id = event.user_id
                message_sending_user_name = self.vk_worker.get_follower_info_by_id(message_sending_user_id).name

                if SECRET_MESSAGE_LINE_ASKING_FOR_PASSWORD in str(event.text):
                    secret = self.mongo_worker.get_user_secret_key_by_id(event.user_id)
                    private_vk.messages.send(
                        user_id=event.user_id,
                        message=f"Here's your password, {message_sending_user_name}: {secret}",
                        random_id=get_random_id(),
                    )
                elif SECRET_MESSAGE_LINE_ASKING_FOR_ACCOUNT_INFO in str(event.text):
                    follower_id = event.user_id
                    surname = self.mongo_worker.get_user_surname_by_id(follower_id)
                    private_vk.messages.send(
                        user_id=event.user_id,
                        message=f"Here's your account info:\nId: {follower_id}\nSurname: {surname}",
                        random_id=get_random_id(),
                    )
                elif any_from_list_in_value(event.text, [*greetings, *russian_greetings]):
                    private_vk.messages.send(
                        user_id=event.user_id,
                        message=f"Hi, {message_sending_user_name}! :)",
                        random_id=get_random_id()
                    )
                else:
                    private_vk.messages.send(
                        user_id=event.user_id,
                        message=f"I'm sorry, {message_sending_user_name}. I don't understand such command yet",
                        random_id=get_random_id()
                    )

    # process messages sent to public group-users chat
    def listen_public_messages(self):
        Utils.log_info("Started listening public messages")
        public_longpoll = VkBotLongPoll(self.vk_session, MY_GROUP_ID)
        public_vk = self.vk_session.get_api()

        keyboard = get_keyboard()

        for event in public_longpoll.listen():
            if event.type == VkBotEventType.MESSAGE_NEW and event.from_chat:
                print(event.message)
                follower_id = event.message["from_id"]
                text = event.message["text"]
                attachments = event.message["attachments"]
                follower_name = self.vk_worker.get_follower_info_by_id(follower_id).name
                if SECRET_MESSAGE_LINE_ASKING_FOR_PASSWORD in str(text):
                    public_vk.messages.send(
                        key=LONG_POLL_KEY,
                        server=LONG_POLL_SERVER,
                        ts=LONG_POLL_TS,
                        random_id=get_random_id(),
                        message=f"{follower_name}, I can't give you your secret key here, cause it's a private info. \n"
                                f"Please write me in private community messages",
                        chat_id=event.chat_id
                    )
                elif len(attachments) == 1 and attachments[0]["type"] == "audio_message":
                    public_vk.messages.send(
                        key=LONG_POLL_KEY,
                        server=LONG_POLL_SERVER,
                        ts=LONG_POLL_TS,
                        random_id=get_random_id(),
                        message=f"{follower_name}, I don't want to listen to your stupid audio_message!",
                        chat_id=event.chat_id
                    )
                elif any_from_list_in_value(text, [*greetings, *russian_greetings]):
                    public_vk.messages.send(
                        key=LONG_POLL_KEY,
                        server=LONG_POLL_SERVER,
                        ts=LONG_POLL_TS,
                        random_id=get_random_id(),
                        message=f"Hello, {follower_name}!",
                        chat_id=event.chat_id
                    )
                elif 'Keyboard' in str(text):
                    public_vk.messages.send(
                        keyboard=keyboard.get_keyboard(),
                        key=LONG_POLL_KEY,
                        server=LONG_POLL_SERVER,
                        ts=LONG_POLL_TS,
                        random_id=get_random_id(),
                        message='User asked to show keyboard',
                        chat_id=event.chat_id
                    )
