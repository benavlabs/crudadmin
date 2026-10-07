"""Regression tests for the admin password length rule.

The old rule was an ungrouped regex alternation, so any password containing a
single letter or digit (``"a"``, ``"1"``) was accepted.
"""

import pytest
from pydantic import ValidationError

from crudadmin.admin_user.schemas import AdminUserCreate, AdminUserUpdate


@pytest.mark.parametrize("password", ["a", "1", "abc", "x!", "seven77", "", "a" * 129])
def test_create_rejects_passwords_outside_the_length_limits(password):
    with pytest.raises(ValidationError):
        AdminUserCreate(username="admin", password=password)


@pytest.mark.parametrize("password", ["a", "1", "seven77", "a" * 129])
def test_update_rejects_passwords_outside_the_length_limits(password):
    with pytest.raises(ValidationError):
        AdminUserUpdate(password=password)


@pytest.mark.parametrize("password", ["admin123", "correct horse battery", "a" * 128])
def test_passwords_within_the_limits_are_accepted(password):
    assert AdminUserCreate(username="admin", password=password).password == password
    assert AdminUserUpdate(password=password).password == password


def test_update_without_a_password_is_still_valid():
    assert AdminUserUpdate(username="renamed").password is None
