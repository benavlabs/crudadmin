"""RedisConfig, the connection settings of the redis session backend."""

import pytest
from pydantic import ValidationError

from crudadmin import RedisConfig


def test_a_url_is_split_into_its_parts():
    config = RedisConfig(
        url="redis://ops:s3cret@cache.internal:6390/3", pool_size=4, connect_timeout=2
    )

    assert config.to_dict() == {
        "host": "cache.internal",
        "port": 6390,
        "db": 3,
        "username": "ops",
        "password": "s3cret",
        "pool_size": 4,
        "connect_timeout": 2,
    }


def test_a_bare_url_falls_back_to_the_defaults():
    assert RedisConfig(url="redis://").to_dict() == {
        "host": "localhost",
        "port": 6379,
        "db": 0,
    }


def test_separate_fields_are_used_without_a_url():
    config = RedisConfig(host="cache", port=6400, db=2, username="ops", password="pw")

    assert config.to_dict() == {
        "host": "cache",
        "port": 6400,
        "db": 2,
        "username": "ops",
        "password": "pw",
    }


@pytest.mark.parametrize("field", ["url", "host", "username", "password"])
def test_a_blank_string_counts_as_unset(field):
    assert getattr(RedisConfig(**{field: "   "}), field) is None


@pytest.mark.parametrize(
    "kwargs",
    [{"port": 0}, {"db": -1}, {"pool_size": 0}, {"connect_timeout": 0}, {"extra": 1}],
)
def test_out_of_range_or_unknown_values_are_refused(kwargs):
    with pytest.raises(ValidationError):
        RedisConfig(**kwargs)
