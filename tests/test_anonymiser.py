from urllib.parse import urlparse

import pytest
from pydantic import HttpUrl

from pyhon.diagnostic import Anonymiser


@pytest.mark.parametrize(
    "data",
    (
        "2024-01-01T00:00:00.0Z",
        "ab-cd-ef-ab-cd-ef",
        "xxxx2024-01-01T00:00:00.0ZYYYYYYYYY",
        "YYYYYYYYYyab-cd-ef-ab-cd-efxxxxxx",
    ),
)
@pytest.mark.parametrize(
    "processor",
    (
        lambda x: x,
        lambda x: {"a": {"b": {"c": x}}},
        lambda x: {"a": {"b": ["c", x]}},
    ),
)
def test_anonymisation_by_string_value(data, processor):
    assert Anonymiser().anonymise(processor(data)) != processor(data)


@pytest.mark.parametrize(
    ("data", "modified_part"),
    (
        ("https://www.example.com/1234/aa-bb-cc-dd-ee-ff", "path"),
        ("https://www.example.com/1234/2012-12-12T14:00:00Z", "path"),
        ("https://www.example.com/aa-bb-cc-dd-ee-ff", "path"),
        ("https://www.example.com/2012-12-12T14:00:00Z", "path"),
        ("https://www.example.com/1234?code=someCode", "query"),
        ("https://www.example.com/1234?macAddress=bb-aa-cc-dd-ff-ee", "query"),
    ),
)
def test_anonymisation_by_url_value(data, modified_part):
    result = Anonymiser().anonymise({"url": HttpUrl(data)})["url"]

    secret_url = urlparse(str(data))._asdict()
    anonymised_url = urlparse(str(result))._asdict()

    assert secret_url.pop(modified_part) != anonymised_url.pop(modified_part)

    for key in secret_url:
        assert secret_url[key] == anonymised_url[key]


@pytest.mark.parametrize(
    "key",
    (
        "serialNumber",
        "code",
        "nickName",
        "mobileId",
        "PK",
        "lat",
        "lng",
        "macAddress",
    ),
)
@pytest.mark.parametrize(
    "value",
    (
        1234,
        1234.567,
        "some-text",
    ),
)
def test_anonymisation_by_key(key, value):
    assert Anonymiser().anonymise({key: value}) != {key: value}
