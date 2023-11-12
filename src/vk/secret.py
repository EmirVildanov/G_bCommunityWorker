import json
from random import randint
from urllib.request import urlopen

from src.vk.model import PublicFollowerInfo


def generate_follower_secret_key(follower_info: PublicFollowerInfo):
    """Generate password for follower with which it can retrieve its personal information.
       Password is built of:
       * name of a dog breed
       * 3 random digits."""
    dog_api_breeds_url = "https://dog.ceo/api/breeds/list/all"
    all_breeds_response = urlopen(dog_api_breeds_url)
    breeds_json_representation = json.loads(all_breeds_response.read())
    breeds = []
    for item in breeds_json_representation["message"]:
        if len(breeds_json_representation["message"][item]) != 0:
            for sub_item in breeds_json_representation["message"][item]:
                breeds.append(f"{item}_{sub_item}")
        else:
            breeds.append(item)

    def random_digit():
        return randint(0, 9)

    return f"{breeds[follower_info.id % len(breeds)]}_{random_digit()}{random_digit()}{random_digit()}"