from datetime import datetime, timezone
from .constants import SNOWFLAKE_EPOCH_MS


def snowflake_to_datetime(snowflake: str) -> datetime:
    ms = (int(snowflake) >> 22) + SNOWFLAKE_EPOCH_MS
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
