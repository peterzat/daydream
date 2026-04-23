"""Smoke test: package imports and version is set."""

import pytest

import daydream

pytestmark = pytest.mark.tier_short


def test_package_imports():
    assert daydream.__version__ == "0.0.1"
