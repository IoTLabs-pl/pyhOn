from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pyhon.commands import HonCommand
    from pyhon.parameter.base import HonParameter


@dataclass
class HonRule:
    trigger_key: str
    trigger_value: str
    param_key: str
    param_data: dict[str, str]
    extras: dict[str, str] | None = None


class HonRuleSet:
    def __init__(self, command: "HonCommand", rule: dict[str, Any]):
        self._command: "HonCommand" = command
        self._rules: dict[str, list[HonRule]] = {}
        self._parse_rule(rule)

    @property
    def rules(self) -> dict[str, list[HonRule]]:
        return self._rules

    def _parse_rule(self, rule: dict[str, Any]) -> None:
        for param_key, params in rule.items():
            param_key = self._command.appliance.options.get(param_key, param_key)
            for trigger_key, trigger_data in params.items():
                self._parse_conditions(param_key, trigger_key, trigger_data)

    def _parse_conditions(
        self,
        param_key: str,
        trigger_key: str,
        trigger_data: dict[str, Any],
        extra: dict[str, str] | None = None,
    ) -> None:
        trigger_key = trigger_key.replace("@", "")
        trigger_key = self._command.appliance.options.get(trigger_key, trigger_key)
        for multi_trigger_value, param_data in trigger_data.items():
            for trigger_value in multi_trigger_value.split("|"):
                if isinstance(param_data, dict):
                    if "typology" in param_data:
                        self._create_rule(
                            param_key, trigger_key, trigger_value, param_data, extra
                        )
                    if extra is None:
                        extra = {}
                    extra[trigger_key] = trigger_value
                    for extra_key, extra_data in param_data.items():
                        self._parse_conditions(param_key, extra_key, extra_data, extra)
                else:
                    param_data = {"typology": "fixed", "fixedValue": param_data}
                    self._create_rule(
                        param_key, trigger_key, trigger_value, param_data, extra
                    )

    def _create_rule(
        self,
        param_key: str,
        trigger_key: str,
        trigger_value: str,
        param_data: dict[str, str],
        extras: dict[str, str] | None = None,
    ) -> None:
        if param_data.get("fixedValue") != f"@{param_key}":
            self._rules.setdefault(trigger_key, []).append(
                HonRule(trigger_key, trigger_value, param_key, param_data, extras)
            )

    def _duplicate_for_extra_conditions(self) -> None:
        new: dict[str, list[HonRule]] = {}
        for rules in self._rules.values():
            for rule in rules:
                if rule.extras is not None:
                    for key, value in rule.extras.items():
                        extras = rule.extras.copy()
                        extras.pop(key)
                        extras[rule.trigger_key] = rule.trigger_value
                        new.setdefault(key, []).append(
                            HonRule(key, value, rule.param_key, rule.param_data, extras)
                        )

        for key, rules in new.items():
            for rule in rules:
                self._rules.setdefault(key, []).append(rule)

    def _extra_rules_matches(self, rule: HonRule) -> bool:
        if rule.extras:
            for key, value in rule.extras.items():
                if not (pvalue := self._command.parameters.get(key)):
                    return False
                if str(pvalue) != str(value):
                    return False
        return True

    def _add_trigger(self, parameter: "HonParameter", data: HonRule) -> None:
        def apply(rule: HonRule) -> None:
            if self._extra_rules_matches(rule):
                if param := self._command.parameters.get(rule.param_key):
                    if fixed_value := rule.param_data.get("fixedValue", ""):
                        param.apply_fixed_value(fixed_value)
                    elif rule.param_data.get("typology") == "enum":
                        param.apply_rule(rule)

        parameter.add_trigger(data.trigger_value, apply, data)

    def patch(self) -> None:
        self._duplicate_for_extra_conditions()
        for name, parameter in self._command.parameters.items():
            if name in self._rules:
                for data in self._rules.get(name, []):
                    self._add_trigger(parameter, data)
