from typing import Literal

from ._base import ApplianceEndpoint, ResponseModel


class SendResponse(ResponseModel):
    result_code: Literal["0"]


SendEndpoint = ApplianceEndpoint(
    url="/send",
    response_model=SendResponse,
)
