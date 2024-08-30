from typing import TYPE_CHECKING

from .enum import EnumParameter

if TYPE_CHECKING:
    from pyhon.commands import HonCommand


class ProgramParameter(EnumParameter):
    _FILTER = ["iot_recipe", "iot_guided"]

    def __init__(self, key: str, command: "HonCommand", group: str) -> None:
        super().__init__(key, {}, group)
        self._command = command
        if "PROGRAM" in command.category:
            self._value = command.category.rsplit(".", 1)[-1].lower()
        else:
            self._value = command.category
        self._programs: dict[str, "HonCommand"] = command.categories
        self._typology: str = "enum"

    @property
    def value(self) -> str | float:
        return self._value

    @value.setter
    def value(self, value: str) -> None:
        if value in self.values:
            self._command.category = value
        else:
            raise ValueError(f"Allowed values: {self.values} But was: {value}")

    @property
    def values(self) -> list[str]:
        return sorted(
            v for v in self._programs if all(f not in v for f in self._FILTER)
        )

    @values.setter
    def values(self, values: list[str]) -> None:
        self._values = values

    @property
    def ids(self) -> dict[int, str]:
        values: dict[int, str] = {}
        for name, parameter in self._programs.items():
            if "iot_" not in name:
                if parameter.parameters.get("prCode"):
                    if (
                        not (fav := parameter.parameters.get("favourite"))
                        or fav.value != "1"
                    ):
                        values[int(parameter.parameters["prCode"].value)] = name
        return dict(sorted(values.items()))
