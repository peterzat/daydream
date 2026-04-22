"""Smoke test: package imports and version is set."""

import daydream


def test_package_imports():
    assert daydream.__version__ == "0.0.1"
