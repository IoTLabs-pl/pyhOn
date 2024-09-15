import random
import re
from collections.abc import Generator
from datetime import datetime
from itertools import groupby
from string import ascii_lowercase, ascii_uppercase, digits
from typing import Any, Callable, Self, TypeVar, cast, overload

_KeyT = str | int
_PrimiviteT = _KeyT | float
_PrimiviteGenericT = TypeVar("_PrimiviteGenericT", bound=_PrimiviteT)
_JsonT = dict[str, "_JsonT"] | list["_JsonT"] | _PrimiviteT
_FlattenedJsonKeyT = tuple[_KeyT, ...]
_FlattenedJsonT = dict[_FlattenedJsonKeyT, _PrimiviteT]


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
}

_FIFTY_YEARS = 50 * 365 * 24 * 60 * 60


class DictTool:
    """
    A class for processing nested dictionaries.
    Implements builder pattern, so methods can be chained.
    """

    def __init__(self) -> None:
        """Initialize the Processor with an empty randoms dictionary and no data."""
        self._randoms: dict[_PrimiviteT, _PrimiviteT] = {}
        self.__data: _FlattenedJsonT | None = None

    def load(self, data: Any) -> Self:
        """
        Load data into the Processor.

        Args:
            data (dict | list): The data to be loaded.

        Returns:
            Processor: The instance of the Processor.
        """
        self.__data = {k: v for k, v in self.__leaf_items(data)}
        return self

    @staticmethod
    def __leaf_items(data: _JsonT) -> Generator[tuple[_FlattenedJsonKeyT, _PrimiviteT]]:
        """
        Recursively yield leaf items from a nested dictionary or list.

        Args:
            data (Any): The nested dictionary or list.

        Yields:
            Generator[tuple[tuple[str | int, ...], Any]]: Tuples of keys and values.
        """
        if isinstance(data, dict | list):
            items = data.items() if isinstance(data, dict) else enumerate(data)
            for key, value in items:
                for subkey, subvalue in DictTool.__leaf_items(value):
                    yield (cast(_KeyT, key), *subkey), subvalue
        else:
            yield (), data

    @staticmethod
    def __inflate(data: _FlattenedJsonT) -> _JsonT:
        """
        Inflate a flattened dictionary back into a nested structure.

        Args:
            data (dict): The flattened dictionary.

        Returns:
            dict | list: The nested structure.
        """
        key = next(iter(data.keys()))
        if len(key) == 0:
            return data[key]

        groups = {
            key: {k[1:]: v for k, v in group}
            for key, group in groupby(data.items(), key=lambda x: x[0][0])
        }

        inflated = {key: DictTool.__inflate(group) for key, group in groups.items()}

        return list(inflated.values()) if isinstance(key[0], int) else inflated

    @property
    def _data(self) -> _FlattenedJsonT:
        """
        Get the loaded data.

        Returns:
            dict: The loaded data.

        Raises:
            ValueError: If no data is loaded.
        """
        if self.__data is None:
            raise ValueError("Data not loaded")
        return self.__data

    def get_flat_result(self) -> dict[str, _PrimiviteT]:
        """
        Get the processed result in a flattened form. After calling this method, the data is cleared.

        Returns:
            dict: The processed result.
        """
        r = {".".join(map(str, k)): v for k, v in self._data.items()}
        self.__data = None
        return r

    def get_result(self) -> Any:
        """
        Get the processed result. After calling this method, the data is cleared.

        Args:
            flatten (bool): Whether to return the result in a flattened form.

        Returns:
            dict | list: The processed result.
        """
        r = DictTool.__inflate(self._data)
        self.__data = None
        return r

    @overload
    def __randomize(self, secret: re.Match[str], by: Callable[[str], str]) -> str: ...
    @overload
    def __randomize(
        self, secret: _PrimiviteGenericT, by: Callable[[str], str]
    ) -> _PrimiviteGenericT: ...
    def __randomize(
        self, secret: re.Match[str] | _PrimiviteT, by: Callable[[str], str]
    ) -> _PrimiviteT:
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
    def __randomize_value(self, s: _PrimiviteGenericT) -> _PrimiviteGenericT: ...
    def __randomize_value(self, s: re.Match[str] | _PrimiviteT) -> _PrimiviteT:
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

    def anonymize(self) -> Self:
        """
        Anonymize data by replacing restricted keys with random values.

        Returns:
            Processor: The instance of the Processor.
        """
        for k, v in self._data.items():
            direct_key = k[-1]
            if direct_key in _RESTRICTED_KEYS:
                v = self.__randomize_value(v)

            elif isinstance(v, str):
                for regex, randomizer in (
                    (_MAC_REGEX, self.__randomize_value),
                    (_TIMESTAMP_REGEX, self.__randomize_date),
                ):
                    v = regex.sub(randomizer, v)

                if v.startswith("http"):
                    for pair in v.split("&"):
                        key, _, value = pair.partition("=")
                        if key in _RESTRICTED_KEYS:
                            v = v.replace(value, self.__randomize_value(value))

            self._data[k] = v

        return self

    def remove_empty(self) -> Self:
        """
        Remove empty values from the data.

        Returns:
            Processor: The instance of the Processor.
        """
        self.__data = {k: v for k, v in self._data.items() if v}
        return self
