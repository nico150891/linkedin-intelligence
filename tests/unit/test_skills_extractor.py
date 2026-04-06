"""Tests for the skills extractor module."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from linkedin_intelligence.extractors.skills import SkillsExtractor
from linkedin_intelligence.providers.base import ExtractedSkills


def test_sample_jobs_jsonl_is_valid(sample_jobs_path: Path) -> None:
    """Verify that jobs_sample.jsonl contains valid JSON lines."""
    lines = sample_jobs_path.read_text().strip().splitlines()
    assert len(lines) == 10, f"Expected 10 sample jobs, got {len(lines)}"
    for i, line in enumerate(lines):
        record = json.loads(line)
        assert "id" in record, f"Job at line {i} missing 'id'"
        assert "skills_tecnicas" in record, f"Job at line {i} missing 'skills_tecnicas'"
        assert "tecnologias" in record, f"Job at line {i} missing 'tecnologias'"


def test_load_processed_ids_empty(tmp_path: Path) -> None:
    """No cache file => empty processed IDs."""
    provider = AsyncMock()
    extractor = SkillsExtractor(provider, tmp_path)
    assert extractor._processed_ids == set()


def test_load_processed_ids_from_cache(tmp_path: Path) -> None:
    """Existing cache file loads IDs correctly."""
    cache_file = tmp_path / "jobs_enriched.jsonl"
    cache_file.write_text('{"id": "111", "title": "A"}\n{"id": "222", "title": "B"}\n')
    provider = AsyncMock()
    extractor = SkillsExtractor(provider, tmp_path)
    assert extractor._processed_ids == {"111", "222"}


def test_load_raw_jobs_from_file(tmp_path: Path) -> None:
    """Load raw jobs from a single JSONL file."""
    jobs_file = tmp_path / "jobs.jsonl"
    jobs_file.write_text(
        '{"id": "1", "description": "Python developer needed"}\n'
        '{"id": "2", "description": "Java engineer role"}\n'
    )
    provider = AsyncMock()
    extractor = SkillsExtractor(provider, tmp_path)
    jobs = extractor._load_raw_jobs(jobs_file)
    assert len(jobs) == 2


def test_load_raw_jobs_from_directory(tmp_path: Path) -> None:
    """Load raw jobs from multiple JSONL files in a directory."""
    jobs_dir = tmp_path / "scraped"
    jobs_dir.mkdir()
    (jobs_dir / "a.jsonl").write_text('{"id": "1", "description": "Job A"}\n')
    (jobs_dir / "b.jsonl").write_text('{"id": "2", "description": "Job B"}\n')
    provider = AsyncMock()
    extractor = SkillsExtractor(provider, tmp_path)
    jobs = extractor._load_raw_jobs(jobs_dir)
    assert len(jobs) == 2


@pytest.mark.asyncio()
async def test_extract_batch_skips_processed(tmp_path: Path) -> None:
    """Already-processed jobs are skipped."""
    cache_file = tmp_path / "jobs_enriched.jsonl"
    cache_file.write_text('{"id": "1", "title": "Already done"}\n')

    jobs_file = tmp_path / "raw.jsonl"
    desc = "Python developer with 5 years experience needed for our team"
    jobs_file.write_text(f'{{"id": "1", "description": "{desc}"}}\n')

    provider = AsyncMock()
    extractor = SkillsExtractor(provider, tmp_path)
    count = await extractor.extract_batch(jobs_file)

    assert count == 0
    provider.extract_skills.assert_not_called()


@pytest.mark.asyncio()
async def test_extract_batch_processes_new_jobs(tmp_path: Path) -> None:
    """New jobs are extracted and appended to cache."""
    jobs_file = tmp_path / "raw.jsonl"
    desc = (
        "We need a senior Python developer with expertise in"
        " machine learning, TensorFlow, and cloud infrastructure"
    )
    jobs_file.write_text(f'{{"id": "42", "description": "{desc}"}}\n')

    mock_provider = AsyncMock()
    mock_provider.extract_skills.return_value = ExtractedSkills(
        skills_tecnicas=["Python", "ML"],
        skills_blandas=["teamwork"],
        tecnologias=["TensorFlow"],
        industria="Tech",
        seniority="senior",
        remote=False,
    )

    extractor = SkillsExtractor(mock_provider, tmp_path)
    count = await extractor.extract_batch(jobs_file)

    assert count == 1
    mock_provider.extract_skills.assert_called_once()

    # Verify cache was written
    cache = tmp_path / "jobs_enriched.jsonl"
    assert cache.exists()
    record = json.loads(cache.read_text().strip())
    assert record["id"] == "42"
    assert record["skills_tecnicas"] == ["Python", "ML"]


@pytest.mark.asyncio()
async def test_extract_batch_skips_short_descriptions(tmp_path: Path) -> None:
    """Jobs with descriptions shorter than 100 chars are skipped."""
    jobs_file = tmp_path / "raw.jsonl"
    jobs_file.write_text('{"id": "99", "description": "Short"}\n')

    provider = AsyncMock()
    extractor = SkillsExtractor(provider, tmp_path)
    count = await extractor.extract_batch(jobs_file)

    assert count == 0
    provider.extract_skills.assert_not_called()


def test_load_enriched_jobs(tmp_path: Path) -> None:
    """Load enriched jobs from the cache."""
    cache = tmp_path / "jobs_enriched.jsonl"
    cache.write_text(
        '{"id": "1", "skills_tecnicas": ["Python"]}\n{"id": "2", "skills_tecnicas": ["Java"]}\n'
    )
    provider = AsyncMock()
    extractor = SkillsExtractor(provider, tmp_path)
    jobs = extractor.load_enriched_jobs()
    assert len(jobs) == 2
    assert jobs[0]["id"] == "1"
