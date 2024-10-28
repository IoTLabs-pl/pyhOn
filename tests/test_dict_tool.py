from urllib.parse import urlparse

import pytest
from httpx import URL

from pyhon.diagnostic._dict_tools import DictTool


@pytest.mark.parametrize(
    "data",
    (
        {},
        {"a": []},
        {"a": 1, "b": 2, "c": 3},
        {"a": {}},
        {"a": 1, "b": 2},
        {"a": {"b": 1}},
        {"a": {"b": {"c": 1}}},
        {"a": {"b": {"c": 1}, "d": 2}},
        {"a": {"b": {"c": 1}, "d": 2, "e": 3}},
        {"a": [{"b": 1}, {"c": 2}]},
        {"a": [1, 2, 3]},
    ),
)
def test_inflater(data):
    assert DictTool().load(data).get_result() == data


@pytest.mark.parametrize(
    ["data", "expected"],
    (
        ({}, {}),
        ({"a": []}, {"a": []}),
        ({"a": {}}, {"a": {}}),
        ({"a": 1, "b": 2}, {"a": 1, "b": 2}),
        ({"a": 1, "b": 2, "c": 3}, {"a": 1, "b": 2, "c": 3}),
        ({"a": {"b": 1}}, {"a.b": 1}),
        ({"a": {"b": {"c": 1}}}, {"a.b.c": 1}),
        ({"a": {"b": {"c": 1}, "d": 2}}, {"a.b.c": 1, "a.d": 2}),
        ({"a": {"b": {"c": 1}, "d": 2, "e": 3}}, {"a.b.c": 1, "a.d": 2, "a.e": 3}),
        ({"a": [{"b": 1}, {"c": 2}]}, {"a.0.b": 1, "a.1.c": 2}),
        ({"a": [1, 2, 3]}, {"a.0": 1, "a.1": 2, "a.2": 3}),
    ),
)
def test_flattener(data, expected):
    assert DictTool().load(data).get_flat_result() == expected


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
    assert DictTool().load(processor(data)).anonymize().get_result() != processor(data)


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
    result = DictTool().load({"url": URL(data)}).anonymize().get_result()["url"]

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
    assert DictTool().load({key: value}).anonymize().get_result() != {key: value}


@pytest.mark.parametrize(
    ("data", "expected"),
    (
        ({"a": [], "b": 1}, {"b": 1}),
        ({"a": {}, "b": 1}, {"b": 1}),
    ),
)
def test_empty_values_removed(data, expected):
    assert DictTool().load(data).remove_empty().get_result() == expected
