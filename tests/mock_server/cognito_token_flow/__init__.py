import json
from pathlib import Path
from string import Template
from typing import Protocol

from httpx import Request, Response
from respx import MockRouter


class _CognitoTokenFlowData(Protocol):
    id_token: str
    cognito_token: str
    iot_core_token: str


class CognitoTokenFlow:
    CWD = Path(__file__).parent

    def __init__(self, router: MockRouter, data: _CognitoTokenFlowData):
        self.data = data

        self._setup_cognito_token_endpoint(router)

    def _setup_cognito_token_endpoint(self, router: MockRouter):
        router.post(
            "https://api-iot.he.services/auth/v1/login",
            name="cognito-token-endpoint",
        ).mock(side_effect=self._mock_cognito_token_response)

    def _mock_cognito_token_response(self, req: Request) -> Response:
        required_params = {"appVersion", "mobileId", "os", "osVersion", "deviceModel"}

        content = json.loads(req.content)

        if (
            all(param in content for param in required_params)
            and req.headers.get("id-token") == self.data.id_token
        ):
            code = 200
            content_template = "success.json"
        else:
            code = 401
            content_template = "error.json"

        return Response(
            code,
            json=json.loads(
                Template((self.CWD / content_template).read_text()).safe_substitute(
                    cognito_token=self.data.cognito_token,
                    iot_core_token=self.data.iot_core_token,
                )
            ),
        )
