from typing import Any

from .base import Parameter


class FixedParameter(Parameter):
    def __init__(self, key: str, attributes: dict[str, Any], group: str) -> None:
        super().__init__(key, attributes, group)
        self._value: str | float = ""
        self._set_attributes()

    def _set_attributes(self) -> None:
        super()._set_attributes()
        self._value = self._attributes.get("fixedValue", "")

    @property
    def _allowed_values_repr(self) -> str:
        return "fixed"

    @property
    def value(self) -> str | float:
        return self._value if self._value != "" else "0"

    @value.setter
    def value(self, value: str | float) -> None:
        # Fixed values seems being not so fixed as thought
        self._value = value
        self.check_trigger(value)

    def more_options(self, other: Parameter) -> Parameter:
        if not isinstance(other, FixedParameter):
            return self

        return super().more_options(other)
