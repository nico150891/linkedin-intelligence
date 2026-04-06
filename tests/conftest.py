"""Shared fixtures for tests."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture()
def sample_data_path() -> Path:
    """Return the path to the sample data directory."""
    return Path(__file__).parent.parent / "data" / "sample"


@pytest.fixture()
def sample_gdpr_path(sample_data_path: Path) -> Path:
    """Return the path to sample GDPR CSV files."""
    return sample_data_path / "gdpr"


@pytest.fixture()
def sample_jobs_path(sample_data_path: Path) -> Path:
    """Return the path to the sample jobs JSONL file."""
    return sample_data_path / "jobs_sample.jsonl"
