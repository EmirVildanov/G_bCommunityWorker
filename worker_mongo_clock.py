import threading

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

from src.configuration import MINUTES_INTERVAL
from src.db.mongo_worker import MongoWorker
from src.vk.vk_bot import VkBot

sched = BlockingScheduler()


@sched.scheduled_job(IntervalTrigger(minutes=MINUTES_INTERVAL))
def timed_job():
    MongoWorker().made_interval_activity_filling_action()


if __name__ == "__main__":
    sched.start()
