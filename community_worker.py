import threading
import time
from src.configuration import *
from src.mongo.mongo_worker import MongoWorker
from src.vk.vk_bot import VkBot


class CommunityWorker:
    @staticmethod
    def vk_bot_worker_function():
        vk_bot = VkBot()
        vk_bot.start_work()

    @staticmethod
    def activity_tracker_worker_function():
        mongo_worker = MongoWorker()
        while True:
            mongo_worker.made_interval_activity_filling_action()
            time.sleep(MINUTES_INTERVAL * 60)

    def run(self):
        vk_bot_thread = threading.Thread(target=self.vk_bot_worker_function, daemon=True)
        vk_bot_thread.start()
        self.activity_tracker_worker_function()


if __name__ == '__main__':
    CommunityWorker().run()
