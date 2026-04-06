"""Skills extractor with incremental cache, batching, and progress display."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from rich.progress import Progress, SpinnerColumn, TimeElapsedColumn

if TYPE_CHECKING:
    from pathlib import Path

    from linkedin_intelligence.providers.base import ExtractedSkills, LLMProvider

logger = logging.getLogger(__name__)

_BATCH_SIZE = 10


class SkillsExtractor:
    """Extract skills from job descriptions using an LLM provider.

    Features:
    - Incremental cache: already-processed job IDs are skipped.
    - Batched concurrency via asyncio.Semaphore.
    - Rich progress bar for long runs.
    - Append-only JSONL output.
    """

    def __init__(self, provider: LLMProvider, processed_path: Path) -> None:
        self._provider = provider
        self._cache_path = processed_path / "jobs_enriched.jsonl"
        self._processed_ids: set[str] = self._load_processed_ids()

    def _load_processed_ids(self) -> set[str]:
        """Read existing JSONL and return the set of already-processed IDs."""
        if not self._cache_path.exists():
            return set()
        ids: set[str] = set()
        with self._cache_path.open() as f:
            for line in f:
                try:
                    record = json.loads(line)
                    job_id = record.get("id", "")
                    if job_id:
                        ids.add(str(job_id))
                except json.JSONDecodeError:
                    continue
        return ids

    def _load_raw_jobs(self, jobs_path: Path) -> list[dict[str, object]]:
        """Load raw jobs from JSONL files in the given directory."""
        jobs: list[dict[str, object]] = []
        if jobs_path.is_file():
            with jobs_path.open() as f:
                for line in f:
                    try:
                        jobs.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        elif jobs_path.is_dir():
            for jsonl_file in sorted(jobs_path.glob("*.jsonl")):
                with jsonl_file.open() as f:
                    for line in f:
                        try:
                            jobs.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        return jobs

    async def _extract_one(
        self,
        job: dict[str, object],
        semaphore: asyncio.Semaphore,
    ) -> dict[str, object] | None:
        """Extract skills for a single job, respecting the semaphore."""
        description = str(job.get("description", ""))
        if len(description) < 100:
            logger.debug("Skipping job %s: description too short", job.get("id"))
            return None

        async with semaphore:
            try:
                extracted: ExtractedSkills = await self._provider.extract_skills(description)
            except Exception:
                logger.exception("Failed to extract skills for job %s", job.get("id"))
                return None

        enriched: dict[str, object] = {
            **{k: v for k, v in job.items()},
            "skills_tecnicas": extracted.skills_tecnicas,
            "skills_blandas": extracted.skills_blandas,
            "tecnologias": extracted.tecnologias,
            "industria": extracted.industria,
            "seniority": extracted.seniority,
            "remote": extracted.remote,
            "extracted_at": datetime.now(tz=UTC).isoformat(),
            "extraction_provider": type(self._provider).__name__,
        }
        return enriched

    def _append_to_cache(self, record: dict[str, object]) -> None:
        """Append a single enriched record to the JSONL cache."""
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        with self._cache_path.open("a") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    async def extract_batch(self, jobs_path: Path) -> int:
        """Extract skills for all pending jobs. Returns count of newly processed."""
        all_jobs = self._load_raw_jobs(jobs_path)
        pending = [j for j in all_jobs if str(j.get("id", "")) not in self._processed_ids]

        logger.info(
            "%d jobs pending, %d already processed",
            len(pending),
            len(all_jobs) - len(pending),
        )

        if not pending:
            return 0

        semaphore = asyncio.Semaphore(_BATCH_SIZE)
        processed_count = 0

        with Progress(
            SpinnerColumn(),
            *Progress.get_default_columns(),
            TimeElapsedColumn(),
        ) as progress:
            task = progress.add_task("Extracting skills...", total=len(pending))

            for job in pending:
                result = await self._extract_one(job, semaphore)
                if result is not None:
                    self._append_to_cache(result)
                    job_id = str(result.get("id", ""))
                    self._processed_ids.add(job_id)
                    processed_count += 1
                progress.advance(task)

        logger.info("Extracted skills for %d new jobs", processed_count)
        return processed_count

    def load_enriched_jobs(self) -> list[dict[str, object]]:
        """Load all enriched jobs from the cache."""
        if not self._cache_path.exists():
            return []
        jobs: list[dict[str, object]] = []
        with self._cache_path.open() as f:
            for line in f:
                try:
                    jobs.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return jobs
