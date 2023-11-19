from src.utils import Utils
from src.vk.vk_bot import VkWorker

if __name__ == "__main__":
    Utils.init()
    try:
        vk_worker = VkWorker()
        vk_worker.start_work()
    except Exception as e:
        Utils.log_error("HIGH_LEVEL_ERROR_HANDLING", e)
        raise e
