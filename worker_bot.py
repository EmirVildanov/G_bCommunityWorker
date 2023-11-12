from src.vk.vk_bot import VkBot

if __name__ == "__main__":
    vk_bot = VkBot()
    vk_bot.start_work(listen_events=True)
