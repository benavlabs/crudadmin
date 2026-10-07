"""Regression tests: PasswordTransformer never stores a plaintext password."""

import pytest
from pydantic import BaseModel

from crudadmin.admin_interface.model_view import PasswordTransformer


class UserForm(BaseModel):
    username: str
    password: str


def test_a_hash_function_is_required():
    with pytest.raises(ValueError, match="hash_function"):
        PasswordTransformer()


def test_create_and_update_store_only_the_hash():
    transformer = PasswordTransformer(hash_function=lambda p: f"hashed:{p}")
    form = UserForm(username="u", password="plain-secret")

    created = transformer.transform_create_data(form.model_dump(), form)
    updated = transformer.transform_update_data(form.model_dump(), form)

    for data in (created, updated):
        assert data["hashed_password"] == "hashed:plain-secret"
        assert "plain-secret" not in [
            v for k, v in data.items() if k != "hashed_password"
        ]
        assert "password" not in data
