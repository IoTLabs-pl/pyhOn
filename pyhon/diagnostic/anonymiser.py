import random
import re
from datetime import datetime
from string import ascii_lowercase, ascii_uppercase, digits
from typing import Callable, TypeVar, overload

from pydantic import HttpUrl

_PrimitiveT = str | int | float
T = TypeVar("T")


_MAC_REGEX = re.compile(r"[0-9A-Fa-f]{2}(-[0-9A-Fa-f]{2}){5}")
_TIMESTAMP_REGEX = re.compile(r"[\d-]{10}T[\d:]{8}(.\d+)?Z")
_CHAR_REPLACEMENTS = {
    ch: group for group in (ascii_lowercase, ascii_uppercase, digits) for ch in group
}
_RESTRICTED_KEYS = {
    "serialNumber",
    "code",
    "nickName",
    "mobileId",
    "PK",
    "lat",
    "lng",
    "macAddress",
}

_FIFTY_YEARS = 50 * 365 * 24 * 60 * 60


class Anonymiser:
    """
    A class for processing nested dictionaries.
    """

    def __init__(self) -> None:
        self._randoms: dict[_PrimitiveT, _PrimitiveT] = {}

    @overload
    def __randomize(self, secret: re.Match[str], by: Callable[[str], str]) -> str: ...
    @overload
    def __randomize(
        self, secret: _PrimitiveT, by: Callable[[str], str]
    ) -> _PrimitiveT: ...
    def __randomize(
        self, secret: re.Match[str] | _PrimitiveT, by: Callable[[str], str]
    ) -> _PrimitiveT:
        """
        Randomize a value using a provided function.

        Args:
            secret (_T): The value to be randomized.
            by (Callable[[str], str]): The random value factory.

        Returns:
            _T: The randomized value.
        """
        if isinstance(secret, re.Match):
            secret = secret[0]

        if secret not in self._randoms:
            val, t = str(secret), type(secret)
            self._randoms[secret] = t(by(val))
        return self._randoms[secret]

    def __randomize_date(self, m: re.Match[str] | str) -> str:
        """
        Randomize a date string.

        Args:
            m (re.Match | str): The date string or regex match to be randomized.

        Returns:
            str: The randomized date string.
        """
        return self.__randomize(
            m,
            lambda _: datetime.fromtimestamp(random.random() * _FIFTY_YEARS).isoformat(
                timespec="seconds"
            )
            + ".0Z",
        )

    @overload
    def __randomize_value(self, s: re.Match[str]) -> str: ...
    @overload
    def __randomize_value(self, s: _PrimitiveT) -> _PrimitiveT: ...
    def __randomize_value(self, s: re.Match[str] | _PrimitiveT) -> _PrimitiveT:
        """
        Randomize a value by replacing characters.

        Args:
            s (_T): The value to be randomized.

        Returns:
            _T: The randomized value.
        """
        return self.__randomize(
            s,
            lambda secret: "".join(
                random.choice(_CHAR_REPLACEMENTS.get(ch, ch)) for ch in secret
            ),
        )

    def __randomize_string(self, s: str) -> str:
        """
        Randomize a string by replacing mac adresses and dates.

        Args:
            s (str): The string to be randomized.

        Returns:
            str: The randomized string
        """
        for regex, randomizer in (
            (_MAC_REGEX, self.__randomize_value),
            (_TIMESTAMP_REGEX, self.__randomize_date),
        ):
            s = regex.sub(randomizer, s)
        return s

    def anonymise(self, data: T) -> T:
        """
        Anonymize data by replacing restricted keys with random values.

        Returns:
            DictTool: The instance of the DictTool.
        """
        if isinstance(data, list):
            return [self.anonymise(v) for v in data]
        elif isinstance(data, dict):
            return {
                k: self.__randomize_value(v)
                if k in _RESTRICTED_KEYS
                else self.anonymise(v)
                for k, v in data.items()
            }
        elif isinstance(data, str):
            return self.__randomize_string(data)
        elif isinstance(data, HttpUrl):
            path = "/".join(
                self.__randomize_string(part) for part in data.path.split("/") if part
            )
            if data.query:
                query = "&".join(
                    f"{k}={self.__randomize_value(v) if k in _RESTRICTED_KEYS else v}"
                    for k, v in data.query_params()
                )
            else:
                query = None

            return HttpUrl.build(
                scheme=data.scheme,
                host=data.host,
                port=data.port,
                fragment=data.fragment,
                password=data.password,
                username=data.username,
                path=path,
                query=query,
            )
        else:
            return data
