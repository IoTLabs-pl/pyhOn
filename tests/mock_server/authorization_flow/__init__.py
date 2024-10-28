import json
from functools import partial
from pathlib import Path
from string import Template
from typing import Protocol

from httpx import Request, Response
from respx import MockRouter, utils


class _AuthorizationFlowData(Protocol):
    username: str
    password: str
    access_token: str
    refresh_token: str
    id_token: str


class AuthorizationFlow:
    CWD = Path(__file__).parent

    def __init__(self, router: MockRouter, data: _AuthorizationFlowData):
        self.data = data

        self._setup_login_page(router)
        self._setup_login_endpoint(router)
        self._setup_post_login_redirects(router)

    def _setup_login_page(self, router: MockRouter):
        login_page = router.get(
            url="https://account2.hon-smarthome.com/services/oauth2/authorize/expid_Login",
            name="login-page",
        )
        for i in range(2):
            url = f"https://account2.hon-smarthome.com/login_redirect_{i}"
            login_page.respond(302, headers={"Location": url})
            login_page = router.get(url, name=f"login-redirect-{i}")

        login_page.respond(200, html=(self.CWD / "login_page.html").read_text())

    def _setup_login_endpoint(self, router: MockRouter):
        router.post(
            "https://account2.hon-smarthome.com/s/sfsites/aura?r=3&other.LightningLoginCustom.login=1",
            name="login-endpoint",
        ).mock(side_effect=self._mock_login_response)

    def _mock_login_response(self, req: Request) -> Response:
        try:
            data, _ = utils.decode_data(req)
            params = json.loads(data["message"])["actions"][0]["params"]
            assert params["username"] == self.data.username
            assert params["password"] == self.data.password

            content_source = "success.json"
        except Exception:
            content_source = "error.json"

        template = Template((self.CWD / content_source).read_text())
        json_content = template.safe_substitute(
            target="https://account2.hon-smarthome.com/post_success_redirect_0.html"
        )

        return Response(200, json=json.loads(json_content))

    def _setup_post_login_redirects(self, router: MockRouter):
        for i in range(2):
            path_template = "/post_success_redirect_{i}.html"

            current_path = path_template.format(i=i)
            next_path = path_template.format(i=i + 1)

            template = Template((self.CWD / current_path.strip("/")).read_text())
            html = template.safe_substitute(
                base_url="https://account2.hon-smarthome.com", target=next_path
            )

            router.get(
                f"https://account2.hon-smarthome.com{current_path}",
                name=f"post-success-redirect{i}",
            ).respond(200, html=html)

        router.get(
            url=f"https://account2.hon-smarthome.com{next_path}",
            name="token-page",
        ).mock(side_effect=partial(self._mock_post_login_tokens, template=template))

    def _mock_post_login_tokens(self, _req: Request, template: Template) -> Response:
        return Response(
            200,
            html=template.safe_substitute(
                target="hon://mobilesdk/detect/oauth/done"
                f"#access_token={self.data.access_token}"
                f"&refresh_token={self.data.refresh_token}"
                "&instance_url=https%3A%2F%2Fhaiereurope.my.salesforce.com"
                "&id=https%3A%2F%2Flogin.salesforce.com%2Fid%2FSOME_OTHER_ID%2FSOME_IDAAA"
                "&issued_at=1727271000000"
                "&signature=SOME_SIGNATURE%2FSOME_SIGNATURE%3D"
                "&sfdc_community_url=https%3A%2F%2Faccount2.hon-smarthome.com"
                "&sfdc_community_id=SOME_COMMUNITY_ID"
                f"&id_token={self.data.id_token}"
                "&scope=api+web+refresh_token+openid"
                "&token_type=Bearer",
            ),
        )
