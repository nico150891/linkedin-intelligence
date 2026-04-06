"""Market statistics aggregation from enriched jobs and recruiter messages."""

from __future__ import annotations

import json
import logging
from collections import Counter
from typing import TYPE_CHECKING

from linkedin_intelligence.providers.base import IndustryCount, MarketStats, SkillCount

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)


def _top_counts(counter: Counter[str], n: int = 15) -> list[SkillCount]:
    """Return the top-n items from a Counter as SkillCount list."""
    return [SkillCount(name=name, count=count) for name, count in counter.most_common(n)]


def _top_industries(counter: Counter[str], n: int = 10) -> list[IndustryCount]:
    """Return the top-n industries from a Counter."""
    return [IndustryCount(name=name, count=count) for name, count in counter.most_common(n)]


def _load_jsonl(path: Path) -> list[dict[str, object]]:
    """Load records from a JSONL file."""
    if not path.exists():
        return []
    records: list[dict[str, object]] = []
    with path.open() as f:
        for line in f:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def compute_stats(
    enriched_jobs_path: Path,
    recruiter_signals_path: Path | None = None,
) -> MarketStats:
    """Aggregate market statistics from enriched jobs and recruiter signals.

    Args:
        enriched_jobs_path: Path to jobs_enriched.jsonl
        recruiter_signals_path: Optional path to recruiter_signals.jsonl

    Returns:
        MarketStats with aggregated data.
    """
    jobs = _load_jsonl(enriched_jobs_path)

    # --- Job-based stats ---
    tech_counter: Counter[str] = Counter()
    skill_counter: Counter[str] = Counter()
    industry_counter: Counter[str] = Counter()
    seniority_counter: Counter[str] = Counter()
    remote_count = 0
    total = len(jobs)

    for job in jobs:
        tecnologias = job.get("tecnologias")
        if isinstance(tecnologias, list):
            for t in tecnologias:
                if isinstance(t, str) and t.strip():
                    tech_counter[t.strip()] += 1

        skills = job.get("skills_tecnicas")
        if isinstance(skills, list):
            for s in skills:
                if isinstance(s, str) and s.strip():
                    skill_counter[s.strip()] += 1

        industria = job.get("industria")
        if isinstance(industria, str) and industria.strip() and industria != "unknown":
            industry_counter[industria.strip()] += 1

        seniority = job.get("seniority")
        if isinstance(seniority, str) and seniority.strip():
            seniority_counter[seniority.strip()] += 1

        remote = job.get("remote")
        if remote is True:
            remote_count += 1

    seniority_dist: dict[str, float] = {}
    if total > 0:
        for level, count in seniority_counter.items():
            seniority_dist[level] = round(count / total * 100, 1)

    remote_pct = round(remote_count / total * 100, 1) if total > 0 else 0.0

    # --- Recruiter signal stats ---
    recruiter_role_counter: Counter[str] = Counter()
    recruiter_skill_counter: Counter[str] = Counter()
    recruiter_industry_counter: Counter[str] = Counter()
    inbound_count = 0

    if recruiter_signals_path is not None:
        signals = _load_jsonl(recruiter_signals_path)
        inbound_count = len(signals)

        for signal in signals:
            roles = signal.get("roles")
            if isinstance(roles, list):
                for r in roles:
                    if isinstance(r, str) and r.strip():
                        recruiter_role_counter[r.strip()] += 1

            skills_mentioned = signal.get("skills")
            if isinstance(skills_mentioned, list):
                for s in skills_mentioned:
                    if isinstance(s, str) and s.strip():
                        recruiter_skill_counter[s.strip()] += 1

            industry = signal.get("industry")
            if isinstance(industry, str) and industry.strip():
                recruiter_industry_counter[industry.strip()] += 1

    stats = MarketStats(
        top_tecnologias=_top_counts(tech_counter),
        top_skills_tecnicas=_top_counts(skill_counter),
        top_industrias=_top_industries(industry_counter),
        seniority_distribution=seniority_dist,
        remote_pct=remote_pct,
        recruiter_mentioned_roles=_top_counts(recruiter_role_counter),
        recruiter_mentioned_skills=_top_counts(recruiter_skill_counter),
        inbound_recruiter_count=inbound_count,
        top_recruiter_industries=_top_industries(recruiter_industry_counter),
    )

    logger.info(
        "Stats computed from %d jobs: %d technologies, %d skills, %.1f%% remote",
        total,
        len(tech_counter),
        len(skill_counter),
        remote_pct,
    )
    return stats
