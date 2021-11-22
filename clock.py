import threading

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

from src.configuration import MINUTES_INTERVAL
from src.mongo.mongo_worker import MongoWorker
from src.vk.vk_bot import VkBot

sched = BlockingScheduler()


@sched.scheduled_job(IntervalTrigger(minutes=MINUTES_INTERVAL))
def timed_job():
    MongoWorker().made_interval_activity_filling_action()


def vk_bot_worker_function():
    vk_bot = VkBot()
    vk_bot.start_work()


if __name__ == "__main__":
    vk_bot_thread = threading.Thread(target=vk_bot_worker_function, daemon=True)
    vk_bot_thread.start()
    sched.start()
