import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..apis.dto.command.descriptor import Command as CommandDescriptorDTO
from ..apis.dto.command.descriptor import SimpleCommand, VariantCommand
from ..apis.dto.command.parameter import FixedParameter
from ..apis.dto.command.payload import CommandPayload as CommandPayloadDTO

if TYPE_CHECKING:
    from .appliance import Appliance


@dataclass
class Command:
    descriptor: CommandDescriptorDTO
    appliance: "Appliance" = field(repr=False)

    # payload: CommandPayloadDTO = field(default=None)

    @classmethod
    async def fetch(cls, appliance: "Appliance"):
        commands_response, _history_response, _favourites_response = await asyncio.gather(
            appliance.api.retrieve(appliance=appliance),
            appliance.api.history(appliance=appliance),
            appliance.api.favourites(appliance=appliance),
        )
        # TODO: Why we need to fetch commands history?
        # historical_payloads = {
        #     item.command.command_name: item.command
        #     for item in sorted(
        #         history_response.history, key=lambda it: it.timestamp_executed
        #     )
        # }
        # TODO: Favourites not implemented at the moment
        # look at: @file pyhon/apis/dto/favourite.py
        # https://github.com/Andre0512/pyhOn/blob/59e3d9949f8a342e05daba70451196e7497cacb2/pyhon/command_loader.py#L184
        # (await appliance.api.favourites(appliance=appliance)).favourites

        commands = [
            cls(
                descriptor=cmd,
                appliance=appliance,
            )
            for cmd in commands_response.commands.values()
        ]

        return commands

    def create_payload_template(self) -> CommandPayloadDTO:
        if isinstance(self.descriptor, SimpleCommand):
            parameters = {
                param.key: param.fixed_value
                for param in self.descriptor.parameters.values()
                if param.mandatory and isinstance(param, FixedParameter)
            }

            ancillary_parameters = {
                param.key: param.fixed_value
                for param in self.descriptor.ancillary_parameters.values()
                if param.mandatory and isinstance(param, FixedParameter)
            }

            return CommandPayloadDTO(
                command_name=self.descriptor.key,
                appliance_type=self.appliance.data.appliance_type,
                mac_address=self.appliance.data.mac_address,
                parameters=parameters,
                ancillary_parameters=ancillary_parameters,
            )

    async def execute(self, payload: CommandPayloadDTO):
        return await self.appliance.api.send(appliance=self.appliance, data=payload)
