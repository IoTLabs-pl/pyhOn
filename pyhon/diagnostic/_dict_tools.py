import random
import re
from collections.abc import Generator
from datetime import datetime
from itertools import groupby
from string import ascii_lowercase, ascii_uppercase, digits
from typing import Any, Callable, Never, Self, TypeVar, cast, overload

from yarl import URL

_KeyT = str | int
_PrimiviteT = _KeyT | float | URL
_PrimiviteGenericT = TypeVar("_PrimiviteGenericT", bound=_PrimiviteT)
_JsonT = (
    dict[str, "_JsonT"] | list["_JsonT"] | _PrimiviteT | list[Never] | dict[str, Never]
)
_FlattenedJsonKeyT = tuple[_KeyT, ...]
_FlattenedJsonValueT = _PrimiviteT | list[Never] | dict[str, Never]
_FlattenedJsonT = dict[_FlattenedJsonKeyT, _FlattenedJsonValueT]


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


class DictTool:
    """
    A class for processing nested dictionaries.
    Implements builder pattern, so methods can be chained.
    """

    def __init__(self) -> None:
        """Initialize the DictTool with an empty randoms dictionary and no data."""
        self._randoms: dict[_PrimiviteT, _PrimiviteT] = {}
        self.__data: _FlattenedJsonT | None = None

    def load(self, data: Any) -> Self:
        """
        Load data into the DictTool.

        Args:
            data (dict | list): The data to be loaded.

        Returns:
            DictTool: The instance of the DictTool.
        """
        self.__data = {k: v for k, v in self.__leaf_items(data)}
        return self

    @staticmethod
    def __leaf_items(
        data: _JsonT,
    ) -> Generator[tuple[_FlattenedJsonKeyT, _FlattenedJsonValueT]]:
        """
        Recursively yield leaf items from a nested dictionary or list.

        Args:
            data (Any): The nested dictionary or list.

        Yields:
            Generator[tuple[tuple[str | int, ...], Any]]: Tuples of keys and values.
        """
        if isinstance(data, dict | list) and len(data) > 0:
            items = data.items() if isinstance(data, dict) else enumerate(data)
            for key, value in items:
                for subkey, subvalue in DictTool.__leaf_items(value):
                    yield (cast(_KeyT, key), *subkey), subvalue
        else:
            yield (), cast(_FlattenedJsonValueT, data)

    @staticmethod
    def __inflate(data: _FlattenedJsonT) -> _JsonT:
        """
        Inflate a flattened dictionary back into a nested structure.

        Args:
            data (dict): The flattened dictionary.

        Returns:
            dict | list: The nested structure.
        """
        if set(data) == {()}:
            return data[()]

        groups = {
            key: {k[1:]: v for k, v in group}
            for key, group in groupby(data.items(), key=lambda x: x[0][0])
        }

        inflated = {key: DictTool.__inflate(group) for key, group in groups.items()}

        return (
            list(inflated.values())
            if all(isinstance(key, int) for key in inflated)
            else inflated
        )

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

    def get_flat_result(self) -> dict[str, _FlattenedJsonValueT]:
        """
        Get the processed result in a flattened form. After calling this method, the data is cleared.

        Returns:
            dict: The processed result.
        """

        if set(self._data) == {()}:
            r = cast(dict[str, _FlattenedJsonValueT], self._data[()])
        else:
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
            DictTool: The instance of the DictTool.
        """
        for k, v in self._data.items():
            if isinstance(v, _PrimiviteT):
                if k and k[-1] in _RESTRICTED_KEYS:
                    v = self.__randomize_value(v)

                elif isinstance(v, str):
                    for regex, randomizer in (
                        (_MAC_REGEX, self.__randomize_value),
                        (_TIMESTAMP_REGEX, self.__randomize_date),
                    ):
                        v = regex.sub(randomizer, v)

                elif isinstance(v, URL):
                    v = v % tuple(
                        (k, v.replace(v, self.__randomize_value(v)))
                        for k, v in v.query.items()
                        if k in _RESTRICTED_KEYS
                    )

                self._data[k] = v

        return self

    def remove_empty(self) -> Self:
        """
        Remove empty values from the data.

        Returns:
            DictTool: The instance of the DictTool.
        """
        self.__data = {k: v for k, v in self._data.items() if v}
        return self
