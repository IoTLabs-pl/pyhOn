from typing import Annotated

from pydantic import AfterValidator, AliasPath, Field

from ._base import BaseModel

# TODO: Can mqtt_topic can really be empty?
# TODO: Can nick_name really be empty?
# TODO: Enumerate the appliance types


class Appliance(BaseModel):
    appliance_model_id: int
    appliance_type: Annotated[str, Field(alias="applianceTypeName")]
    brand: Annotated[str, AfterValidator(str.title)]
    code: str
    mac_address: str
    model_name: str
    nick_name: Annotated[str, Field(default="")]
    series: str
    serial_number: str
    fw_version: str
    firmware_id: Annotated[int, Field(alias="eepromId")]
    mqtt_topics: Annotated[
        list[str],
        Field(default=[], alias=AliasPath("topics", "subscribe")),
    ]

    @property
    def slug(self):
        return f"{self.appliance_type}_{self.appliance_model_id}".lower()
