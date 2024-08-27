from contextlib import suppress
from copy import copy
from functools import cached_property
from typing import Dict, Any, Optional, TYPE_CHECKING, List

from pyhon.commands import HonCommand
from pyhon.parameter.program import HonParameterProgram

if TYPE_CHECKING:
    from pyhon.appliance import HonAppliance


class HonCommandLoader:
    """Loads and parses hOn command data"""

    def __init__(
        self,
        appliance: "HonAppliance",
        api_commands_data: dict[str, Any],
        command_history_data: list[dict[str, Any]],
        favourites_data: list[dict[str, Any]],
    ) -> None:
        self._appliance: "HonAppliance" = appliance

        self._api_commands: Dict[str, Any] = api_commands_data
        self._favourites: List[Dict[str, Any]] = favourites_data
        self._command_history: List[Dict[str, Any]] = command_history_data
        self._commands = {}

    @property
    def appliance(self) -> "HonAppliance":
        """appliance object"""
        return self._appliance

    @property
    def commands(self) -> Dict[str, HonCommand]:
        """commands dict"""
        if len(self._commands) == 0:
            self.parse_commands()
        return self._commands

    def parse_commands(self) -> Dict[str, HonCommand]:
        self._commands = {
            command.name: command
            for command in (
                self._parse_command(data, name)
                for name, data in self._api_commands.items()
            )
            if command
        }
        self._add_favourites()
        self._recover_last_command_states()

    @staticmethod
    def _clean_name(category: str) -> str:
        """Clean up category name"""
        if "PROGRAM" in category:
            return category.rsplit(".", 1)[-1].lower()
        return category

    def _parse_command(
        self,
        data: Dict[str, Any] | str,
        command_name: str,
        categories: Optional[Dict[str, "HonCommand"]] = None,
        category_name: str = "",
    ) -> Optional[HonCommand]:
        """Try to create HonCommand object"""
        if isinstance(data, dict):
            if HonCommand.parseable(data):
                return HonCommand(
                    command_name,
                    data,
                    self._appliance,
                    category_name=category_name,
                    categories=categories,
                )
            if category := self._parse_categories(data, command_name):
                return category
        return None

    def _parse_categories(
        self, data: Dict[str, Any], command_name: str
    ) -> Optional[HonCommand]:
        """Parse categories and create reference to other"""
        categories: Dict[str, HonCommand] = {}
        for category, value in data.items():
            if command := self._parse_command(
                value, command_name, category_name=category, categories=categories
            ):
                categories[self._clean_name(category)] = command
        if categories:
            # setParameters should be at first place
            if "setParameters" in categories:
                return categories["setParameters"]
            return list(categories.values())[0]
        return None

    def _get_last_command_index(self, name: str) -> Optional[int]:
        """Get index of last command execution"""
        return next(
            (
                index
                for (index, d) in enumerate(self._command_history)
                if d.get("command", {}).get("commandName") == name
            ),
            None,
        )

    def _set_last_category(
        self, command: HonCommand, name: str, parameters: Dict[str, Any]
    ) -> HonCommand:
        """Set category to last state"""
        if command.categories:
            if program := parameters.pop("program", None):
                command.category = self._clean_name(program)
            elif category := parameters.pop("category", None):
                command.category = category
            else:
                return command
            return self.commands[name]
        return command

    def _recover_last_command_states(self) -> None:
        """Set commands to last state"""
        for name, command in self.commands.items():
            if (last_index := self._get_last_command_index(name)) is not None:
                last_command = self._command_history[last_index]
                parameters = last_command.get("command", {}).get("parameters", {})
                command = self._set_last_category(command, name, parameters)
                for key, data in command.settings.items():
                    if parameters.get(key) is not None:
                        with suppress(ValueError):
                            data.value = parameters.get(key)

    def _add_favourites(self) -> None:
        """Patch program categories with favourites"""
        for favourite in self._favourites:
            name, command_name, base = self._get_favourite_info(favourite)
            if base:
                base_command = copy(base)
                base_command.update(favourite)
                base_command.set_as_favourite()
                self._update_program_categories(command_name, name, base_command)

    def _get_favourite_info(
        self, favourite: Dict[str, Any]
    ) -> tuple[str, str, HonCommand | None]:
        name: str = favourite.get("favouriteName", {})
        command = favourite.get("command", {})
        command_name: str = command.get("commandName", "")
        program_name = self._clean_name(command.get("programName", ""))
        base_command = self.commands[command_name].categories.get(program_name)
        return name, command_name, base_command

    def _update_program_categories(
        self, command_name: str, name: str, base_command: HonCommand
    ) -> None:
        program = base_command.parameters["program"]
        if isinstance(program, HonParameterProgram):
            program.value = name
        self.commands[command_name].categories[name] = base_command
