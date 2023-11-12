import datetime

from dataclasses import dataclass
from typing import Optional


@dataclass
class PrivateFollowerInfo:
    """Follower info that contains fields that we mustn't share with public (e.g. secret key) and that we
       store in the database."""
    id: int
    first_name: str
    last_name: str
    secret_key: str
    is_public: bool


@dataclass
class PublicFollowerInfo:
    """Follower info that does not contain private info and that we can safely show to anybody."""
    id: int
    first_name: str
    last_name: str


@dataclass
class FollowerOnlineStatus:
    """Follower info indicating whether it was online in the chosen `minutes_interval_number` and if was
       what platform was it using."""
    follower_id: int
    minutes_interval_number: int
    # Datetime this information was gathered
    datetime: datetime.datetime
    online: bool
    last_seen_datetime: Optional[datetime.datetime] = None
    platform: Optional[int] = None


@dataclass
class BotMessage:
    """Information about message that was sent to the bot."""
    id: int
    text: str


@dataclass
class CommunityPost:
    text: str
