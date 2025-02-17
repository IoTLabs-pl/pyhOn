from dataclasses import dataclass
from functools import partial
from typing import Any

from httpx import Request, Response
from respx import MockRouter, Route

from pyhon.diagnostic.tool import Dump

from .authorization_flow import AuthorizationFlow
from .cognito_token_flow import CognitoTokenFlow
from .refresh_token_flow import RefreshTokenFlow


@dataclass
class MockServer:
    router: MockRouter

    username: str = "username"
    password: str = "password"

    access_token: str = "access_token"
    refresh_token: str = "refresh_token"
    id_token: str = "id_token"
    cognito_token: str = "cognito_token"
    iot_core_token: str = "iot_core_token"

    def __post_init__(self):
        AuthorizationFlow(self.router, self)
        RefreshTokenFlow(self.router, self)
        CognitoTokenFlow(self.router, self)

    def _is_authorized(self, req: Request) -> bool:
        return (
            req.headers.get("cognito-token") == self.cognito_token
            and req.headers.get("id-token") == self.id_token
        )

    def secure_endpoint(self, req: Request, status_code: int, data: Any) -> Response:
        if not self._is_authorized(req):
            return Response(
                status_code=403,
                json={
                    "Message": (
                        "User is not authorized to access"
                        " this resource with an explicit deny"
                    )
                },
            )

        return Response(status_code=status_code, json=data)

    def install_dump(self, dump: Dump) -> list[Route]:
        return [
            self.router.request(
                call.method,
                str(call.url),
                name=f"{dump.slug}:{call.url_suffix}",
            ).mock(
                side_effect=partial(
                    self.secure_endpoint,
                    status_code=call.status,
                    data=call.content,
                )
            )
            for call in dump.calls
        ]
