import logging
from typing import TYPE_CHECKING, Any

from pyhon.parameter import (
    EnumParameter,
    FixedParameter,
    Parameter,
    ProgramParameter,
    RangeParameter,
)
from pyhon.rules import HonRuleSet

if TYPE_CHECKING:
    from pyhon.appliances import Appliance

_LOGGER = logging.getLogger(__name__)


class HonCommand:
    def __init__(
        self,
        name: str,
        attributes: dict[str, Any],
        appliance: "Appliance",
        category_name: str = "",
        categories: dict[str, "HonCommand"] | None = None,
    ):
        self._name: str = name
        self._appliance: Appliance = appliance
        self._categories: dict[str, HonCommand] | None = categories
        self._category_name: str = category_name
        self._parameters: dict[str, Parameter] = {}
        self._data: dict[str, Any] = {}
        self._rules: list[HonRuleSet] = []
        attributes.pop("description")
        attributes.pop("protocolType")
        self._load_parameters(attributes)

    @property
    def name(self) -> str:
        return self._name

    @property
    def data(self) -> dict[str, Any]:
        return self._data

    @property
    def parameters(self) -> dict[str, Parameter]:
        return self._parameters

    @property
    def appliance(self) -> "Appliance":
        return self._appliance

    def parameter_groups(
        self, mandatory_only: bool = False
    ) -> dict[str, dict[str, str | float]]:
        result: dict[str, dict[str, str | float]] = {}
        for name, parameter in self._parameters.items():
            if not mandatory_only or parameter.mandatory:
                result.setdefault(parameter.group, {})[name] = parameter.intern_value
        return result

    @property
    def parameter_value(self) -> dict[str, str | float]:
        return {n: p.value for n, p in self._parameters.items()}

    def _load_parameters(self, attributes: dict[str, dict[str, Any] | Any]) -> None:
        for key, items in attributes.items():
            if not isinstance(items, dict):
                _LOGGER.info("Loading Attributes - Skipping %s", str(items))
                continue
            for name, data in items.items():
                self._create_parameters(data, name, key)
        for rule in self._rules:
            rule.patch()

    def _create_parameters(
        self, data: dict[str, Any], name: str, parameter: str
    ) -> None:
        if name == "zoneMap" and self._appliance.zone:
            data["default"] = self._appliance.zone
        if data.get("category") == "rule":
            if "fixedValue" in data:
                self._rules.append(HonRuleSet(self, data["fixedValue"]))
            elif "enumValues" in data:
                self._rules.append(HonRuleSet(self, data["enumValues"]))
            else:
                _LOGGER.warning("Rule not supported: %s", data)
        match data.get("typology"):
            case "range":
                self._parameters[name] = RangeParameter(name, data, parameter)
            case "enum":
                self._parameters[name] = EnumParameter(name, data, parameter)
            case "fixed":
                self._parameters[name] = FixedParameter(name, data, parameter)
            case _:
                self._data[name] = data
                return
        if self._category_name:
            name = "program" if "PROGRAM" in self._category_name else "category"
            self._parameters[name] = ProgramParameter(name, self, "custom")

    async def send(self, only_mandatory: bool = False) -> bool:
        grouped_params = self.parameter_groups(only_mandatory)
        params = grouped_params.get("parameters", {})
        return await self.send_parameters(params)

    async def send_specific(self, param_names: list[str]) -> bool:
        params: dict[str, str | float] = {}
        for key, parameter in self._parameters.items():
            if key in param_names or parameter.mandatory:
                params[key] = parameter.value
        return await self.send_parameters(params)

    async def send_parameters(self, params: dict[str, str | float]) -> bool:
        ancillary_params = self.parameter_groups().get("ancillaryParameters", {})
        ancillary_params.pop("programRules", None)
        if "prStr" in params:
            params["prStr"] = self._category_name.upper()
        self._appliance.sync_command_to_params(self.name)
        return await self._appliance.send_command(
            self._name,
            params,
            ancillary_params,
            self._category_name,
        )

    @property
    def categories(self) -> dict[str, "HonCommand"]:
        if self._categories is None:
            return {"_": self}
        return self._categories

    @categories.setter
    def categories(self, categories: dict[str, "HonCommand"]) -> None:
        self._categories = categories

    @property
    def category(self) -> str:
        return self._category_name

    @category.setter
    def category(self, category: str) -> None:
        if category in self.categories:
            self._appliance.commands[self._name] = self.categories[category]

    @property
    def setting_keys(self) -> list[str]:
        return list(
            {param for cmd in self.categories.values() for param in cmd.parameters}
        )

    @property
    def available_settings(self) -> dict[str, Parameter]:
        result: dict[str, Parameter] = {}
        for command in self.categories.values():
            for name, parameter in command.parameters.items():
                if name in result:
                    result[name] = result[name].more_options(parameter)
                else:
                    result[name] = parameter
        return result

    def reset(self) -> None:
        for parameter in self._parameters.values():
            parameter.reset()

    @staticmethod
    def parseable(data: Any) -> bool:
        """Check if dict can be parsed as command"""
        return (
            isinstance(data, dict)
            and data.get("description") is not None
            and data.get("protocolType") is not None
        )

    def update(self, data: dict[str, str | dict[str, Any]]) -> None:
        """Update command with new data"""
        for d in data.values():
            if not isinstance(d, str):
                for key, value in d.items():
                    if parameter := self.parameters.get(key):
                        parameter.value = value

    def set_as_favourite(self) -> None:
        """Set command as favourite"""
        self.parameters.update(
            favourite=FixedParameter("favourite", {"fixedValue": "1"}, "custom")
        )
