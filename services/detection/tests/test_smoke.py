"""Phase 00 smoke test: interpreter policy and package import."""

import sys

import sentinelx_detection


def test_python_version_matches_policy() -> None:
    assert sys.version_info >= (3, 12)


def test_package_imports() -> None:
    assert sentinelx_detection.__doc__
