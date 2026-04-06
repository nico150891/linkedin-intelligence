"""Tests for the stats analysis module."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from linkedin_intelligence.analysis.stats import compute_stats


def test_sample_jobs_have_required_fields(sample_jobs_path: Path) -> None:
    """Verify that sample jobs contain all fields needed for stats aggregation."""
    required_fields = {"industria", "seniority", "remote", "tecnologias", "skills_tecnicas"}
    for line in sample_jobs_path.read_text().strip().splitlines():
        record = json.loads(line)
        missing = required_fields - set(record.keys())
        assert not missing, f"Job {record.get('id')} missing fields: {missing}"


def test_compute_stats_from_sample(sample_jobs_path: Path) -> None:
    """Stats aggregation runs correctly on sample data."""
    stats = compute_stats(sample_jobs_path)
    assert len(stats.top_tecnologias) > 0
    assert len(stats.top_skills_tecnicas) > 0
    assert len(stats.top_industrias) > 0
    assert stats.remote_pct >= 0.0


def test_compute_stats_empty(tmp_path: Path) -> None:
    """Stats from an empty file returns zero-value MarketStats."""
    empty_file = tmp_path / "empty.jsonl"
    empty_file.write_text("")
    stats = compute_stats(empty_file)
    assert stats.top_tecnologias == []
    assert stats.remote_pct == 0.0


def test_compute_stats_nonexistent_file(tmp_path: Path) -> None:
    """Stats from nonexistent file returns zero-value MarketStats."""
    stats = compute_stats(tmp_path / "missing.jsonl")
    assert stats.top_tecnologias == []


def test_compute_stats_seniority_distribution(sample_jobs_path: Path) -> None:
    """Seniority distribution sums to ~100%."""
    stats = compute_stats(sample_jobs_path)
    total = sum(stats.seniority_distribution.values())
    assert 99.0 <= total <= 101.0  # Allow rounding tolerance


def test_compute_stats_with_recruiter_signals(tmp_path: Path) -> None:
    """Recruiter signal stats are aggregated when provided."""
    jobs_file = tmp_path / "jobs.jsonl"
    jobs_file.write_text(
        '{"id":"1","tecnologias":["Python"],"skills_tecnicas":["ML"],'
        '"industria":"Tech","seniority":"senior","remote":true}\n'
    )
    signals_file = tmp_path / "signals.jsonl"
    signals_file.write_text(
        '{"roles":["ML Engineer"],"skills":["Python","TensorFlow"]}\n'
        '{"roles":["Data Scientist"],"skills":["Python"]}\n'
    )
    stats = compute_stats(jobs_file, recruiter_signals_path=signals_file)
    assert stats.inbound_recruiter_count == 2
    assert len(stats.recruiter_mentioned_roles) > 0
    assert len(stats.recruiter_mentioned_skills) > 0


def test_compute_stats_remote_percentage(tmp_path: Path) -> None:
    """Remote percentage is calculated correctly."""
    jobs_file = tmp_path / "jobs.jsonl"
    jobs_file.write_text(
        '{"id":"1","tecnologias":[],"skills_tecnicas":[],"industria":"A","seniority":"mid","remote":true}\n'
        '{"id":"2","tecnologias":[],"skills_tecnicas":[],"industria":"B","seniority":"mid","remote":false}\n'
        '{"id":"3","tecnologias":[],"skills_tecnicas":[],"industria":"C","seniority":"mid","remote":true}\n'
    )
    stats = compute_stats(jobs_file)
    assert stats.remote_pct == pytest.approx(66.7, abs=0.1)
