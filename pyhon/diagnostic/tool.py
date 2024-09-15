import asyncio
import datetime
import json
import zipfile
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from pyhon import __version__
from pyhon.appliances import Appliance
from pyhon.parameter import EnumParameter, RangeParameter

from ._dict_tools import DictTool

if TYPE_CHECKING:
    from aiohttp import ClientResponse

    from pyhon.apis import API


@dataclass
class CallData:
    invoker: str
    response: "ClientResponse"
    processor: Callable[[dict[str, Any]], dict[str, Any]] = lambda x: x

    @property
    def filename(self) -> str:
        return f'{self.response.url.path.rsplit("/", 1).pop()}.json'

    @property
    def metadata(self) -> dict[str, Any]:
        return self.processor(
            {
                "url": str(self.response.url),
                "method": self.response.method,
                "status": self.response.status,
                "invoker": self.invoker,
                "filename": self.filename,
            }
        )

    async def payload(self) -> dict[str, Any]:
        return self.processor(await self.response.json())


class Diagnoser:
    """
    Diagnoser class to handle appliance diagnostics and data dumping.

    Attributes:
        appliance (Appliance): The appliance instance.
        api_calls (dict): Dictionary to store API call data.
    """

    @classmethod
    async def from_raw_api_data(
        cls, api: "API", directory: Path, anonymous: bool = True, as_zip: bool = False
    ) -> None:
        """
        Create Diagnoser instances from raw API data.

        Args:
            api (API): The API instance.
            directory (Path): The directory to save the data.
            anonymous (bool, optional): Whether to anonymize the data. Defaults to True.
            as_zip (bool, optional): Whether to save the data as a zip file. Defaults to False.

        Returns:
            List[Diagnoser]: List of Diagnoser instances.
        """
        session = api._session  # noqa: SLF001

        async with session.history_tracker:
            loader = api.load_appliances_data
            appliances_data = await loader()

            diagnosers = [
                cls(
                    Appliance(api, data),
                    CallData(loader.__qualname__, session._history[-1]),  # noqa: SLF001
                )
                for data in appliances_data
            ]

        for diagnoser in diagnosers:
            await diagnoser.api_dump(directory, anonymous, as_zip)

    def __init__(
        self,
        appliance: "Appliance",
        factory_call_data: CallData | None = None,
    ):
        """
        Initialize the Diagnoser instance.

        Args:
            appliance (Appliance): The appliance instance.
            factory_call_data (CallMeta, optional): The factory call data. Defaults to None.
        """
        self.appliance = appliance
        self.call_data: list[CallData] = []
        if factory_call_data:
            self.call_data.append(factory_call_data)

    @contextmanager
    def __artifacts_container(
        self, parent: Path, as_zip: bool
    ) -> Generator[zipfile.Path | Path]:
        """
        Context manager to handle artifact container creation.

        Args:
            parent (Path): The parent directory.
            as_zip (bool): Whether to save the data as a zip file.

        Yields:
            Path: The path to the artifact container.
        """
        artifact_name = (
            f"{self.appliance.appliance_type.lower()}_{self.appliance.model_id}"
        )
        if as_zip:
            parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(parent / f"{artifact_name}.zip", "w") as archive:
                yield zipfile.Path(archive)
        else:
            directory = parent / artifact_name
            directory.mkdir()
            yield directory

    def write_files(self, directory: Path, files: dict[str, Any], as_zip: bool) -> None:
        """
        Write files to the specified directory.

        Args:
            directory (Path): The directory to save the files.
            files (dict): Dictionary of files to save.
            as_zip (bool): Whether to save the data as a zip file.
        """
        with self.__artifacts_container(directory, as_zip) as container:
            for name, content in files.items():
                with container.joinpath(name).open("w") as f:
                    json.dump(content, f, indent=2)

    async def api_dump(
        self, directory: Path, anonymous: bool = True, as_zip: bool = False
    ) -> None:
        """
        Dump API data to the specified directory.

        Args:
            directory (Path): The directory to save the data.
            anonymous (bool, optional): Whether to anonymize the data. Defaults to True.
            as_zip (bool, optional): Whether to save the data as a zip file. Defaults to False.
        """
        session = self.appliance._api._session  # noqa: SLF001

        for method in (
            self.appliance.load_commands,
            self.appliance.load_command_history,
            self.appliance.load_attributes,
            self.appliance.load_statistics,
            self.appliance.load_maintenance_cycle,
        ):
            async with session.history_tracker:
                try:
                    await method()
                except Exception:
                    pass
                self.call_data.append(
                    CallData(method.__qualname__, session._history[-1])  # noqa: SLF001
                )

        if anonymous:
            tool = DictTool()
            for call in self.call_data:
                call.processor = lambda x: tool.load(x).anonymize().get_result()

        files = {
            "metadata.json": {
                "timestamp": datetime.datetime.now(tz=datetime.UTC).isoformat(
                    timespec="seconds"
                ),
                "pyhOn_version": __version__,
                "calls": [call.metadata for call in self.call_data],
            }
        } | {call.filename: await call.payload() for call in self.call_data}

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.write_files, directory, files, as_zip)

    def as_dict(self, flat_keys: bool = False, anonymous: bool = True) -> Any:
        """
        Convert the Diagnoser instance to a dictionary.

        Args:
            flat_keys (bool, optional): Whether to flatten the keys. Defaults to False.
            anonymous (bool, optional): Whether to anonymize the data. Defaults to True.

        Returns:
            dict: The dictionary representation of the Diagnoser instance.
        """
        data = {
            "data": self.appliance.data,
            "additional_data": self.appliance.additional_data,
            "attributes": {k: v.value for k, v in self.appliance.attributes.items()},
            "commands": self._build_commands_dict(),
            "rules": self._build_rules_dict(),
            "statistics": self.appliance.statistics,
            "maintenance_cycle": self.appliance.maintenance_cycle,
        }

        processor = DictTool().load(data).remove_empty()
        if anonymous:
            processor.anonymize()

        return processor.get_flat_result() if flat_keys else processor.get_result()

    def _build_commands_dict(self) -> dict[str, Any]:
        """
        Build a dictionary of appliance commands.

        Returns:
            dict: The dictionary of appliance commands.
        """
        return {
            command.name: {
                parameter_name: parameter.values
                for parameter_name, parameter in command.parameters.items()
                if isinstance(parameter, EnumParameter)
            }
            | {
                parameter_name: {
                    "min": parameter.min,
                    "max": parameter.max,
                    "step": parameter.step,
                }
                for parameter_name, parameter in command.parameters.items()
                if isinstance(parameter, RangeParameter)
            }
            for command in self.appliance.commands.values()
        }

    def _build_rules_dict(self) -> dict[str, Any]:
        """
        Build a dictionary of appliance rules.

        Returns:
            dict: The dictionary of appliance rules.
        """
        return {
            command.name: {
                parameter_name: parameter.triggers
                for parameter_name, parameter in command.parameters.items()
                if parameter.triggers
            }
            for command in self.appliance.commands.values()
        }
