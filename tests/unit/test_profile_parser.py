"""Tests for the profile parser module."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest

from linkedin_intelligence.parsers.profile import (
    ProfileParser,
    _calculate_experience_years,
    _find_current_position,
)
from linkedin_intelligence.providers.base import UserProfile, WorkExperience

# ---------------------------------------------------------------------------
# Fixture verification
# ---------------------------------------------------------------------------


def test_profile_csv_has_content(sample_gdpr_path: Path) -> None:
    """Verify that Profile.csv has at least one data row."""
    profile_csv = sample_gdpr_path / "Profile.csv"
    lines = profile_csv.read_text().strip().splitlines()
    assert len(lines) >= 2, "Profile.csv should have a header and at least one data row"


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def test_calculate_experience_years_nonempty() -> None:
    positions = [
        WorkExperience(title="Engineer", company="Co", started_on="2018-01-01", finished_on=None),
        WorkExperience(
            title="Junior", company="Old", started_on="2014-06-01", finished_on="2017-12-31"
        ),
    ]
    years = _calculate_experience_years(positions)
    # From 2014 to current year
    assert years >= 10


def test_calculate_experience_years_empty() -> None:
    assert _calculate_experience_years([]) == 0


def test_find_current_position_with_current() -> None:
    positions = [
        WorkExperience(
            title="Head of AI", company="NovaMind", started_on="2022-01-01", finished_on=None
        ),
        WorkExperience(
            title="Engineer", company="Old", started_on="2019-01-01", finished_on="2021-12-31"
        ),
    ]
    title, company = _find_current_position(positions)
    assert title == "Head of AI"
    assert company == "NovaMind"


def test_find_current_position_all_finished() -> None:
    positions = [
        WorkExperience(
            title="Latest", company="B", started_on="2020-01-01", finished_on="2022-01-01"
        ),
        WorkExperience(
            title="Oldest", company="A", started_on="2018-01-01", finished_on="2019-12-31"
        ),
    ]
    title, company = _find_current_position(positions)
    assert title == "Latest"
    assert company == "B"


def test_find_current_position_empty() -> None:
    title, company = _find_current_position([])
    assert title == "Unknown"
    assert company is None


# ---------------------------------------------------------------------------
# Fake LLM provider for testing
# ---------------------------------------------------------------------------


def _make_fake_provider() -> Any:
    """Create a mock provider that returns realistic LLM inference results."""
    provider = AsyncMock()
    provider.infer_profile_domain.return_value = {
        "domain": "AI/ML",
        "suggested_keywords": [
            "ML engineer",
            "AI lead",
            "NLP engineer",
            "computer vision engineer",
            "MLOps engineer",
        ],
    }
    return provider


# ---------------------------------------------------------------------------
# ProfileParser.parse
# ---------------------------------------------------------------------------


@pytest.mark.asyncio()
async def test_parse_profile_full(sample_gdpr_path: Path) -> None:
    provider = _make_fake_provider()
    parser = ProfileParser(sample_gdpr_path, provider)
    profile = await parser.parse()

    assert isinstance(profile, UserProfile)
    assert profile.full_name == "Alex Rivera"
    assert profile.headline == "Head of AI at NovaMind Labs"
    assert profile.current_role == "Head of AI"
    assert profile.current_company == "NovaMind Labs"
    assert profile.domain == "AI/ML"
    assert profile.experience_years >= 10
    assert len(profile.declared_skills) == 25
    assert "Python" in profile.declared_skills
    assert "PyTorch" in profile.declared_skills
    assert len(profile.experience) == 4
    assert len(profile.suggested_keywords) == 5


@pytest.mark.asyncio()
async def test_parse_profile_calls_llm_once(sample_gdpr_path: Path) -> None:
    provider = _make_fake_provider()
    parser = ProfileParser(sample_gdpr_path, provider)
    await parser.parse()

    provider.infer_profile_domain.assert_called_once()
    call_kwargs = provider.infer_profile_domain.call_args
    assert "Head of AI" in str(call_kwargs)


@pytest.mark.asyncio()
async def test_parse_profile_positions_have_iso_dates(sample_gdpr_path: Path) -> None:
    provider = _make_fake_provider()
    parser = ProfileParser(sample_gdpr_path, provider)
    profile = await parser.parse()

    for pos in profile.experience:
        # ISO format: YYYY-MM-DD
        assert len(pos.started_on) == 10
        assert pos.started_on[4] == "-"
        if pos.finished_on is not None:
            assert len(pos.finished_on) == 10


@pytest.mark.asyncio()
async def test_parse_profile_current_has_no_end_date(sample_gdpr_path: Path) -> None:
    provider = _make_fake_provider()
    parser = ProfileParser(sample_gdpr_path, provider)
    profile = await parser.parse()

    current = next(p for p in profile.experience if p.company == "NovaMind Labs")
    assert current.finished_on is None


@pytest.mark.asyncio()
async def test_parse_profile_missing_profile_csv(tmp_path: Path) -> None:
    provider = _make_fake_provider()
    parser = ProfileParser(tmp_path, provider)

    with pytest.raises(FileNotFoundError, match="Profile.csv not found"):
        await parser.parse()


@pytest.mark.asyncio()
async def test_parse_profile_missing_optional_csvs(tmp_path: Path) -> None:
    """Profile.csv exists but Positions.csv and Skills.csv are missing."""
    profile_csv = tmp_path / "Profile.csv"
    profile_csv.write_text(
        "First Name,Last Name,Maiden Name,Address,Birth Date,Headline,Summary,"
        "Industry,Zip Code,Geo Location,Twitter Handles,Websites,Instant Messengers\n"
        "Test,User,,,1990-01-01,Software Engineer,,Technology,,Madrid Spain,,,\n"
    )

    provider = _make_fake_provider()
    parser = ProfileParser(tmp_path, provider)
    profile = await parser.parse()

    assert profile.full_name == "Test User"
    assert profile.current_role == "Unknown"
    assert profile.declared_skills == []
    assert profile.experience == []


@pytest.mark.asyncio()
async def test_parse_profile_llm_returns_empty_keywords(sample_gdpr_path: Path) -> None:
    """Handle LLM returning no keywords gracefully."""
    provider = AsyncMock()
    provider.infer_profile_domain.return_value = {
        "domain": "Backend",
        "suggested_keywords": [],
    }
    parser = ProfileParser(sample_gdpr_path, provider)
    profile = await parser.parse()

    assert profile.domain == "Backend"
    assert profile.suggested_keywords == []
