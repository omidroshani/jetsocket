"""Shared fixtures for exchange integration tests."""

from __future__ import annotations

import os

import pytest

NETWORK_TESTS_ENABLED = bool(os.environ.get("WSFABRIC_NETWORK_TESTS"))

skip_no_network = pytest.mark.skipif(
    not NETWORK_TESTS_ENABLED,
    reason="Set WSFABRIC_NETWORK_TESTS=1 to run exchange tests",
)
