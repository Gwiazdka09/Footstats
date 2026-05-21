"""Testy resolve_admin_user_id."""
import os

import pytest

os.environ.setdefault("JWT_SECRET", "testsecret1234567890abcdef12345678")
os.environ.setdefault("OPERATOR_ADMIN_USERNAME", "admin")

from footstats.utils.admin_user import (
    clear_admin_user_cache,
    get_operator_admin_username,
    resolve_admin_user_id,
)


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_admin_user_cache()
    yield
    clear_admin_user_cache()


def test_get_operator_admin_username():
    assert get_operator_admin_username() == "admin"


def test_resolve_admin_fallback_or_found():
    uid = resolve_admin_user_id(fallback=1)
    assert isinstance(uid, int)
    assert uid >= 1
