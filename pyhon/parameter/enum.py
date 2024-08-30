from typing import TYPE_CHECKING, Any

from .base import Parameter

if TYPE_CHECKING:
    from pyhon.rules import HonRule


def clean_value(value: str | float) -> str:
    return str(value).strip("[]").replace("|", "_").lower()


class EnumParameter(Parameter):
    def __init__(self, key: str, attributes: dict[str, Any], group: str) -> None:
        super().__init__(key, attributes, group)
        self._default: str | float = ""
        self._value: str | float = ""
        self._values: list[str] = []
        self._set_attributes()
        if self._default and clean_value(self._default.strip("[]")) not in self.values:
            self._values.append(self._default)

    def _set_attributes(self) -> None:
        super()._set_attributes()
        self._default = self._attributes.get("defaultValue", "")
        self._value = self._default or "0"
        self._values = self._attributes.get("enumValues", [])

    @property
    def _allowed_values_repr(self) -> str:
        return f"{{{self.values}}}"

    @property
    def values(self) -> list[str]:
        return [clean_value(value) for value in self._values]

    @values.setter
    def values(self, values: list[str]) -> None:
        self._values = values

    def apply_fixed_value(self, value: str | float) -> None:
        if set(self.values) != {str(value)}:
            self.values = [str(value)]
            super().apply_fixed_value(value)

    def apply_rule(self, rule: "HonRule") -> None:
        if enum_values := rule.param_data.get("enumValues"):
            self.values = enum_values.split("|")
        if default_value := rule.param_data.get("defaultValue"):
            self.value = default_value

    @property
    def intern_value(self) -> str:
        return str(self._value) if self._value is not None else str(self.values[0])

    @property
    def value(self) -> str | float:
        return clean_value(self._value) if self._value is not None else self.values[0]

    @value.setter
    def value(self, value: str) -> None:
        if value in self.values:
            self._value = value
            self.check_trigger(value)
        else:
            raise ValueError(f"Allowed values: {self._values} But was: {value}")

    def sync(self, other: "Parameter") -> None:
        if not isinstance(other, EnumParameter):
            raise ValueError(f"Can't sync {self.__class__} with {other.__class__}")
        self.values = other.values
        super().sync(other)
