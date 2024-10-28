import asyncio
import json
from collections.abc import Generator
from dataclasses import dataclass, field
from datetime import datetime
from functools import cached_property
from hashlib import md5
from pathlib import Path
from shutil import make_archive, rmtree
from typing import TYPE_CHECKING, Any, Callable, TypedDict

from pyhon import __version__
from pyhon.appliances import Appliance
from pyhon.parameter import EnumParameter, RangeParameter

from ._dict_tools import DictTool

if TYPE_CHECKING:
    from httpx import URL, Response

    from pyhon.apis import API


class CallMetadata(TypedDict):
    url: "URL"
    method: str
    status: int
    invoker: str
    filename: str
    md5: str


@dataclass
class CallData:
    invoker: str
    response: "Response"
    __serializer: Callable[[Any], bytes] | None = None

    @property
    def serializer(self) -> Callable[[Any], bytes] | None:
        return self.__serializer

    @serializer.setter
    def serializer(self, value: Callable[[Any], bytes]) -> None:
        assert self.__serializer is None, "Serializer already set"
        self.__serializer = value

    @property
    def filename(self) -> str:
        return f'{self.response.url.path.rsplit("/", 1).pop()}.json'

    @property
    def metadata(self) -> CallMetadata:
        return CallMetadata(
            url=self.response.url,
            method=self.response.request.method,
            status=self.response.status_code,
            invoker=self.invoker,
            filename=self.filename,
            md5=md5(self.serialized).hexdigest(),
        )

    @cached_property
    def serialized(self) -> bytes:
        assert self.__serializer is not None, "Serializer not set"
        return self.__serializer(self.response.json())


class DumpMetadata(TypedDict):
    pyhOn_version: str
    timestamp: str
    slug: str
    calls: list[CallMetadata]


@dataclass
class DumpData:
    slug: str
    calls: list[CallData]
    anonymous: bool
    created_at: datetime = field(default_factory=datetime.now)

    @property
    def metadata(self) -> DumpMetadata:
        return DumpMetadata(
            pyhOn_version=__version__,
            timestamp=self.created_at.isoformat(timespec="seconds"),
            slug=self.slug,
            calls=[call.metadata for call in self.calls],
        )

    @property
    def files(self) -> Generator[tuple[str, str]]:
        dict_tool = DictTool() if self.anonymous else None

        def serializer(data):
            if dict_tool:
                data = dict_tool.load(data).anonymize().get_result()
            return json.dumps(data, indent=2, default=str).encode()

        for call in self.calls:
            call.serializer = serializer
            yield call.filename, call.serialized

        yield "metadata.json", serializer(self.metadata)


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

        with api._session.history_tracker as history:  # noqa: SLF001
            loader = api.load_appliances_data
            appliances_data = await loader()

            diagnosers = [
                cls(
                    Appliance(api, data),
                    CallData(loader.__qualname__, history[-1]),
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

    def write_files(self, directory: Path, dump_data: DumpData, as_zip: bool) -> None:
        """
        Write files to the specified directory.

        Args:
            directory (Path): The directory to save the files.
            dump_data (DumpData): The dump data.
            as_zip (bool): Whether to save the data as a zip file.
        """
        directory /= dump_data.slug
        directory.mkdir()

        for name, content in dump_data.files:
            directory.joinpath(name).write_bytes(content)

        if as_zip:
            make_archive(directory.stem, "zip", directory)
            rmtree(directory)

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

        for method_name in dir(self.appliance):
            if method_name.startswith("load_") and callable(
                method := getattr(self.appliance, method_name)
            ):
                with session.history_tracker as history:
                    try:
                        await method()
                    finally:
                        self.call_data.append(
                            CallData(method.__qualname__, history[-1])
                        )

        dump = DumpData(
            f"{self.appliance.appliance_type.lower()}_{self.appliance.model_id}",
            self.call_data,
            anonymous,
        )

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.write_files, directory, dump, as_zip)

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
