from datetime import datetime

from ._base import BaseModel
from .command.payload import CommandPayload


class HistoryItem(BaseModel):
    timestamp_accepted: datetime
    timestamp_executed: datetime
    last_update: datetime
    command: CommandPayload
