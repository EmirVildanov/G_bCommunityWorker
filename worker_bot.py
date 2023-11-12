import logging

from src.utils import Utils, CustomLoggingLevel
from src.vk.vk_bot import VkBot

if __name__ == "__main__":
    Utils.init()
    try:
        vk_bot = VkBot()
        vk_bot.start_work(listen_events=True)
    except Exception as e:
        Utils.log(str(e), CustomLoggingLevel.Error)
