import pytest
from yarl import URL

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
def test_dict_tool(data):
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
def test_anonymisation_by_value(data, processor):
    assert DictTool().load(processor(data)).anonymize().get_result() != processor(data)


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
@pytest.mark.parametrize(
    "processor",
    (
        lambda k, v: v,
        lambda k, v: URL.build(scheme="http", host="example.com", query={k: v}),
    ),
)
def test_anonymisation_by_key(key, value, processor):
    assert DictTool().load({key: processor(key, value)}).anonymize().get_result() != {
        key: processor(key, value)
    }


@pytest.mark.parametrize(
    ("data", "expected"),
    (
        ({"a": [], "b": 1}, {"b": 1}),
        ({"a": {}, "b": 1}, {"b": 1}),
    ),
)
def test_empty_values_removed(data, expected):
    assert DictTool().load(data).remove_empty().get_result() == expected
