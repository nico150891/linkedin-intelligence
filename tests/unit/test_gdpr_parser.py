"""Tests for the GDPR parser module."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from linkedin_intelligence.parsers.gdpr import (
    GDPRParser,
    _is_recruiter_message,
    _parse_date_flexible,
    _strip_bom,
)

# ---------------------------------------------------------------------------
# Fixture verification
# ---------------------------------------------------------------------------


def test_sample_gdpr_files_exist(sample_gdpr_path: Path) -> None:
    """Verify that all expected sample GDPR CSV files are present."""
    expected_files = [
        "messages.csv",
        "connections.csv",
        "job_applications.csv",
        "Profile.csv",
        "Positions.csv",
        "Skills.csv",
    ]
    for filename in expected_files:
        assert (sample_gdpr_path / filename).exists(), f"Missing sample file: {filename}"


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------


def test_strip_bom_removes_bom() -> None:
    assert _strip_bom("\ufeffhello") == "hello"


def test_strip_bom_noop_without_bom() -> None:
    assert _strip_bom("hello") == "hello"


def test_parse_date_iso_datetime() -> None:
    dt = _parse_date_flexible("2024-01-20 10:30:00")
    assert dt == datetime(2024, 1, 20, 10, 30, 0)  # noqa: DTZ001


def test_parse_date_iso_date() -> None:
    dt = _parse_date_flexible("2024-01-20")
    assert dt == datetime(2024, 1, 20)  # noqa: DTZ001


def test_parse_date_day_month_year() -> None:
    dt = _parse_date_flexible("15 Jan 2024")
    assert dt.year == 2024
    assert dt.month == 1
    assert dt.day == 15


def test_parse_date_month_year() -> None:
    dt = _parse_date_flexible("Jan 2022")
    assert dt.year == 2022
    assert dt.month == 1


def test_parse_date_strips_whitespace() -> None:
    dt = _parse_date_flexible("  2024-06-01  ")
    assert dt.year == 2024


def test_parse_date_invalid_raises() -> None:
    import pytest

    with pytest.raises(ValueError, match="Unable to parse date"):
        _parse_date_flexible("not-a-date")


# ---------------------------------------------------------------------------
# Recruiter detection
# ---------------------------------------------------------------------------


def test_recruiter_message_detected() -> None:
    assert _is_recruiter_message(
        sender="Sarah Johnson",
        user_name="Alex Rivera",
        subject="AI Lead opportunity",
        content="I'm a recruiter at TalentBridge.",
    )


def test_own_messages_not_recruiter() -> None:
    assert not _is_recruiter_message(
        sender="Alex Rivera",
        user_name="Alex Rivera",
        subject="AI Lead opportunity",
        content="I'm interested in the role.",
    )


def test_non_recruiter_message() -> None:
    assert not _is_recruiter_message(
        sender="María García",
        user_name="Alex Rivera",
        subject="Re: DeepMind paper",
        content="Have you seen the new Gemini paper?",
    )


def test_recruiter_keyword_in_content() -> None:
    assert _is_recruiter_message(
        sender="Some Recruiter",
        user_name="Alex Rivera",
        subject="Hello",
        content="We have an exciting opportunity for you.",
    )


def test_recruiter_case_insensitive_user_match() -> None:
    """Sender matching the user name is case-insensitive."""
    assert not _is_recruiter_message(
        sender="alex rivera",
        user_name="Alex Rivera",
        subject="Great opportunity",
        content="I'm a recruiter.",
    )


# ---------------------------------------------------------------------------
# GDPRParser.parse_messages
# ---------------------------------------------------------------------------


def test_parse_messages_returns_all(sample_gdpr_path: Path) -> None:
    parser = GDPRParser(sample_gdpr_path, user_name="Alex Rivera")
    messages = parser.parse_messages()
    assert len(messages) == 25


def test_parse_messages_detects_recruiters(sample_gdpr_path: Path) -> None:
    parser = GDPRParser(sample_gdpr_path, user_name="Alex Rivera")
    messages = parser.parse_messages()
    recruiter_msgs = [m for m in messages if m.is_recruiter]
    # Known recruiter messages in sample: Carlos López, Sarah Johnson,
    # Pedro Sánchez, Rebecca Chen, Thomas Miller, Linda Park, Michael Brown
    assert len(recruiter_msgs) >= 6


def test_parse_messages_dates_are_datetimes(sample_gdpr_path: Path) -> None:
    parser = GDPRParser(sample_gdpr_path, user_name="Alex Rivera")
    messages = parser.parse_messages()
    for msg in messages:
        assert isinstance(msg.date, datetime)


def test_parse_messages_no_duplicates(sample_gdpr_path: Path) -> None:
    parser = GDPRParser(sample_gdpr_path, user_name="Alex Rivera")
    messages = parser.parse_messages()
    keys = [(m.sender, m.date, m.subject) for m in messages]
    assert len(keys) == len(set(keys))


def test_parse_messages_missing_file(tmp_path: Path) -> None:
    parser = GDPRParser(tmp_path, user_name="Test User")
    assert parser.parse_messages() == []


# ---------------------------------------------------------------------------
# GDPRParser.parse_connections
# ---------------------------------------------------------------------------


def test_parse_connections_count(sample_gdpr_path: Path) -> None:
    parser = GDPRParser(sample_gdpr_path)
    connections = parser.parse_connections()
    assert len(connections) == 25


def test_parse_connections_fields(sample_gdpr_path: Path) -> None:
    parser = GDPRParser(sample_gdpr_path)
    connections = parser.parse_connections()
    maria = next(c for c in connections if c.first_name == "María")
    assert maria.last_name == "García"
    assert maria.company == "Google DeepMind"
    assert maria.position == "Research Scientist"
    assert isinstance(maria.connected_on, datetime)


def test_parse_connections_no_duplicates(sample_gdpr_path: Path) -> None:
    parser = GDPRParser(sample_gdpr_path)
    connections = parser.parse_connections()
    emails = [c.email for c in connections if c.email]
    assert len(emails) == len(set(emails))


def test_parse_connections_missing_file(tmp_path: Path) -> None:
    parser = GDPRParser(tmp_path)
    assert parser.parse_connections() == []


# ---------------------------------------------------------------------------
# GDPRParser.parse_job_applications
# ---------------------------------------------------------------------------


def test_parse_job_applications_count(sample_gdpr_path: Path) -> None:
    parser = GDPRParser(sample_gdpr_path)
    apps = parser.parse_job_applications()
    assert len(apps) == 25


def test_parse_job_applications_fields(sample_gdpr_path: Path) -> None:
    parser = GDPRParser(sample_gdpr_path)
    apps = parser.parse_job_applications()
    deepmind = next(a for a in apps if a.company == "Google DeepMind")
    assert deepmind.job_title == "Research Scientist — NLP"
    assert deepmind.status == "Applied"
    assert isinstance(deepmind.application_date, datetime)


def test_parse_job_applications_no_duplicates(sample_gdpr_path: Path) -> None:
    parser = GDPRParser(sample_gdpr_path)
    apps = parser.parse_job_applications()
    keys = [(a.company, a.job_title) for a in apps]
    assert len(keys) == len(set(keys))


def test_parse_job_applications_missing_file(tmp_path: Path) -> None:
    parser = GDPRParser(tmp_path)
    assert parser.parse_job_applications() == []
