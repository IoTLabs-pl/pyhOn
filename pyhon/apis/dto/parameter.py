from datetime import datetime
from typing import Annotated, Generic

from pydantic import Field

from ._base import Data_T, Data_T_Union, KeyedModel


class Parameter(KeyedModel, Generic[Data_T]):
    # parName key is used in MQTT messages
    key: Annotated[str, Field(alias="parName")]
    value: Annotated[Data_T_Union, Field(alias="parNewVal")]
    last_update: datetime
