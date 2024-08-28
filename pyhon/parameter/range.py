from typing import Any
from itertools import count, takewhile

from pyhon.helper import str_to_float
from pyhon.parameter.base import HonParameter


class HonParameterRange(HonParameter):
    def __init__(self, key: str, attributes: dict[str, Any], group: str) -> None:
        super().__init__(key, attributes, group)
        self.min: float = 0
        self.max: float = 0
        self._step: float = 0
        self._default: float = 0
        self._value: float = 0
        self._set_attributes()

    def _set_attributes(self) -> None:
        super()._set_attributes()
        self.min = str_to_float(self._attributes.get("minimumValue", 0))
        self.max = str_to_float(self._attributes.get("maximumValue", 0))
        self._step = str_to_float(self._attributes.get("incrementValue", 0))
        self._default = str_to_float(self._attributes.get("defaultValue", self.min))
        self._value = self._default

    def __repr__(self) -> str:
        return f"{self.__class__} (<{self.key}> [{self.min} - {self.max}])"

    @property
    def step(self) -> float:
        if not self._step:
            return 1
        return self._step

    @step.setter
    def step(self, step: float) -> None:
        self._step = step

    @property
    def value(self) -> str | float:
        return self._value if self._value is not None else self.min

    @value.setter
    def value(self, value: str | float) -> None:
        value = str_to_float(value)
        if self.min <= value <= self.max and not ((value - self.min) * 100) % (
            self.step * 100
        ):
            self._value = value
            self.check_trigger(value)
        else:
            allowed = f"min {self.min} max {self.max} step {self.step}"
            raise ValueError(f"Allowed: {allowed} But was: {value}")

    def apply_fixed_value(self, value: str | float) -> None:
        value = float(value)

        self.min = min(self.min, value)
        self.max = max(self.max, value)

        self.value = value

    @property
    def values(self) -> list[str]:
        return [
            str(v)
            for v in takewhile(lambda x: x <= self.max, count(self.min, self.step))
        ]

    def sync(self, other: "HonParameter") -> None:
        if isinstance(other, HonParameterRange):
            self.min = other.min
            self.max = other.max
            self.step = other.step
        else:
            self.max = int(other.value)
            self.min = int(other.value)
            self.step = 1

        super().sync(other)
