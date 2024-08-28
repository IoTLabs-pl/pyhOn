from contextlib import suppress
from copy import copy
from typing import Any, TYPE_CHECKING

from pyhon.commands import HonCommand
from pyhon.parameter.program import HonParameterProgram

if TYPE_CHECKING:
    from pyhon.appliances import HonAppliance


def _clean_name(category: str) -> str:
    """Clean up category name"""
    return category.rsplit(".", 1)[-1].lower() if "PROGRAM" in category else category


def loader(appliance: "HonAppliance", api_commands_data: dict[str, Any]):
    """Load commands from API data. Command can be a single command, a
    category of commands or additional, non-parsable data"""
    commands = {}
    additional_data = {}

    for command_name, command_data in api_commands_data.items():

        if HonCommand.parseable(command_data):
            commands[command_name] = HonCommand(command_name, command_data, appliance)

        elif isinstance(command_data, dict) and all(
            HonCommand.parseable(possible_category_data)
            for possible_category_data in (command_data.values())
        ):
            categories = {}
            categories |= {
                _clean_name(category_name): HonCommand(
                    command_name,
                    category_data,
                    appliance,
                    category_name=category_name,
                    categories=categories,
                )
                for category_name, category_data in command_data.items()
            }

            commands[command_name] = categories.get(
                "setParameters", next(iter(categories.values()))
            )

        else:
            additional_data[command_name] = command_data

    return commands, additional_data


def _get_favourite_info(
    commands: dict[str, HonCommand], favourite: dict[str, Any]
) -> tuple[str, str, HonCommand | None]:
    name: str = favourite.get("favouriteName", {})
    command = favourite.get("command", {})
    command_name: str = command.get("commandName", "")
    program_name = _clean_name(command.get("programName", ""))
    base_command = commands[command_name].categories.get(program_name)
    return name, command_name, base_command


def _update_program_categories(
    commands: dict[str, HonCommand],
    command_name: str,
    name: str,
    base_command: HonCommand,
) -> None:
    program = base_command.parameters["program"]
    if isinstance(program, HonParameterProgram):
        program.value = name
    commands[command_name].categories[name] = base_command


def add_favourites(
    commands: dict[str, HonCommand], favourites_data: list[dict[str, Any]]
):
    for favourite in favourites_data:
        name, command_name, base = _get_favourite_info(commands, favourite)
        if base:
            base_command = copy(base)
            base_command.update(favourite)
            base_command.set_as_favourite()
            _update_program_categories(commands, command_name, name, base_command)


def _get_last_command(
    command_history_data: list[dict[str, Any]], name: str
) -> int | None:
    """Get last command execution (i.e. first in list returned by API)"""
    return next(
        filter(
            lambda cmd: cmd.get("command", {}).get("commandName") == name,
            command_history_data,
        ),
        None,
    )


def _set_last_category(
    command: HonCommand,
    parameters: dict[str, Any],
):
    """Set category to last state"""
    if command.categories:
        if program := parameters.pop("program", None):
            command.category = _clean_name(program)
        elif category := parameters.pop("category", None):
            command.category = category


def recover_last_command_states(commands: dict[str, HonCommand], command_history_data):
    """Set commands to last state"""
    for name, command in commands.items():
        if (last_command := _get_last_command(command_history_data, name)) is not None:
            parameters = last_command.get("command", {}).get("parameters", {})
            _set_last_category(command, parameters)
            for key, data in command.settings.items():
                if parameters.get(key) is not None:
                    with suppress(ValueError):
                        data.value = parameters.get(key)
