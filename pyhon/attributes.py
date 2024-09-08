from datetime import datetime, timedelta
from typing import Final

from pyhon.helper import str_to_float


class Attribute:
    _LOCK_TIMEOUT: Final = 10

    def __init__(self, data: dict[str, str] | str | int | bool):
        self._value: str = ""
        self._last_update: datetime | None = None
        self._lock_timestamp: datetime | None = None
        self.update(data)

    def __int__(self) -> int:
        return int(self.value)

    def __float__(self) -> float:
        return float(self.value)

    @property
    def value(self) -> float | str:
        """Attribute value"""
        try:
            return str_to_float(self._value)
        except ValueError:
            return self._value

    @value.setter
    def value(self, value: str) -> None:
        self._value = value

    @property
    def last_update(self) -> datetime | None:
        """Timestamp of last api update"""
        return self._last_update

    @property
    def lock(self) -> bool:
        """Shows if value changes are forbidden"""
        if not self._lock_timestamp:
            return False
        lock_until = self._lock_timestamp + timedelta(seconds=self._LOCK_TIMEOUT)
        return lock_until >= datetime.now()

    def __eq__(self, value: object) -> bool:
        if isinstance(value, int):
            value = str(value)

        return self.value == value

    def update(
        self, data: dict[str, str] | str | int | bool, shield: bool = False
    ) -> bool:
        if self.lock and not shield:
            return False
        if shield:
            self._lock_timestamp = datetime.now()
        if isinstance(data, dict):
            self.value = data.get("parNewVal", "")
            try:
                self._last_update = datetime.fromisoformat(data["lastUpdate"])
            except (ValueError, KeyError):
                self._last_update = None
            return True

        if isinstance(data, bool):
            data = int(data)

        self.value = str(data)
        return True

    def __str__(self) -> str:
        return self._value
