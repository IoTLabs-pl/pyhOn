import json
from pathlib import Path
from string import Template
from typing import Protocol

from httpx import Request, Response
from respx import MockRouter


class _RefreshTokenFlowData(Protocol):
    access_token: str
    id_token: str
    refresh_token: str


class RefreshTokenFlow:
    CWD = Path(__file__).parent

    def __init__(self, router: MockRouter, data: _RefreshTokenFlowData):
        self.data = data
        self._setup_refresh_token_endpoint(router)

    def _setup_refresh_token_endpoint(self, router: MockRouter):
        # Mock the refresh token endpoint. It may return an error (bad refresh token) or success
        router.post(
            "https://account2.hon-smarthome.com/services/oauth2/token",
            name="refresh-token-endpoint",
            params__contains={
                "client_id": "3MVG9QDx8IX8nP5T2Ha8ofvlmjLZl5L_gvfbT9.HJvpHGKoAS_dcMN8LYpTSYeVFCraUnV.2Ag1Ki7m4znVO6",
                "grant_type": "refresh_token",
            },
        ).mock(side_effect=self._mock_refresh_token_response)

    def _mock_refresh_token_response(self, req: Request) -> Response:
        if req.url.params.get("refresh_token") == self.data.refresh_token:
            status = 200
            content_template_source = "success.json"
        else:
            status = 400
            content_template_source = "error.json"

        return Response(
            status,
            json=json.loads(
                Template(
                    (self.CWD / content_template_source).read_text()
                ).safe_substitute(
                    access_token=self.data.access_token,
                    id_token=self.data.id_token,
                )
            ),
        )
