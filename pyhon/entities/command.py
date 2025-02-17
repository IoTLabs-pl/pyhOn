import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..apis.dto.command.descriptor import Command as CommandDescriptorDTO
from ..apis.dto.command.payload import CommandPayload as CommandPayloadDTO

if TYPE_CHECKING:
    from .appliance import Appliance


@dataclass
class Command:
    descriptor: CommandDescriptorDTO
    appliance: "Appliance" = field(repr=False)

    payload: CommandPayloadDTO = field(default=None)

    @classmethod
    async def fetch(cls, appliance: "Appliance"):
        commands_response, history_response = await asyncio.gather(
            appliance.api.retrieve(appliance=appliance),
            appliance.api.history(appliance=appliance),
        )

        historical_payloads = {
            item.command.command_name: item.command
            for item in sorted(
                history_response.history, key=lambda it: it.timestamp_executed
            )
        }

        commands = [
            cls(
                descriptor=cmd,
                appliance=appliance,
                payload=historical_payloads.get(cmd.key),
            )
            for cmd in commands_response.commands
        ]

        # TODO: Favourites not implemented at the moment
        # look at: @file pyhon/apis/dto/favourite.py
        # https://github.com/Andre0512/pyhOn/blob/59e3d9949f8a342e05daba70451196e7497cacb2/pyhon/command_loader.py#L184
        # (await appliance.api.favourites(appliance=appliance)).favourites

        return commands

    async def execute(self):
        return await self.appliance.api.send(
            appliance=self.appliance, command=self.payload
        )
