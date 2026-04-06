"""Profile parser — builds UserProfile from GDPR export CSVs + LLM inference."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from linkedin_intelligence.parsers.gdpr import _parse_date_flexible, _read_csv
from linkedin_intelligence.providers.base import (
    LLMProvider,
    UserProfile,
    WorkExperience,
)

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)


def _calculate_experience_years(positions: list[WorkExperience]) -> int:
    """Calculate total years of experience from positions."""
    if not positions:
        return 0

    earliest: datetime | None = None
    for pos in positions:
        try:
            started = _parse_date_flexible(pos.started_on)
        except ValueError:
            continue
        if earliest is None or started < earliest:
            earliest = started

    if earliest is None:
        return 0

    return max(1, (datetime.now().year - earliest.year))  # noqa: DTZ005


def _find_current_position(
    positions: list[WorkExperience],
) -> tuple[str, str | None]:
    """Return (title, company) of the current position (no finished_on)."""
    for pos in positions:
        if pos.finished_on is None:
            return pos.title, pos.company
    # Fallback: most recent position (first in list if sorted by start desc)
    if positions:
        return positions[0].title, positions[0].company
    return "Unknown", None


class ProfileParser:
    """Build a UserProfile from the GDPR export directory."""

    def __init__(self, gdpr_path: Path, provider: LLMProvider) -> None:
        self._path = gdpr_path
        self._provider = provider

    def _parse_positions(self) -> list[WorkExperience]:
        """Parse Positions.csv into WorkExperience list."""
        csv_path = self._path / "Positions.csv"
        if not csv_path.exists():
            logger.warning("Positions.csv not found at %s", csv_path)
            return []

        rows = _read_csv(csv_path)
        positions: list[WorkExperience] = []

        for row in rows:
            title = row.get("Title", "").strip()
            company = row.get("Company Name", "").strip()
            started = row.get("Started On", "").strip()
            finished = row.get("Finished On", "").strip() or None

            if not title or not started:
                continue

            # Normalize dates to ISO format
            try:
                started_dt = _parse_date_flexible(started)
                started_iso = started_dt.strftime("%Y-%m-%d")
            except ValueError:
                logger.warning("Skipping position with unparseable date: %s", started)
                continue

            finished_iso: str | None = None
            if finished:
                try:
                    finished_dt = _parse_date_flexible(finished)
                    finished_iso = finished_dt.strftime("%Y-%m-%d")
                except ValueError:
                    logger.warning("Ignoring unparseable end date: %s", finished)

            positions.append(
                WorkExperience(
                    title=title,
                    company=company,
                    started_on=started_iso,
                    finished_on=finished_iso,
                )
            )

        return positions

    def _parse_skills(self) -> list[str]:
        """Parse Skills.csv into a list of skill names."""
        csv_path = self._path / "Skills.csv"
        if not csv_path.exists():
            logger.warning("Skills.csv not found at %s", csv_path)
            return []

        rows = _read_csv(csv_path)
        return [row["Name"].strip() for row in rows if row.get("Name", "").strip()]

    def _parse_profile_csv(self) -> tuple[str, str]:
        """Parse Profile.csv and return (full_name, headline)."""
        csv_path = self._path / "Profile.csv"
        if not csv_path.exists():
            msg = f"Profile.csv not found at {csv_path}"
            raise FileNotFoundError(msg)

        rows = _read_csv(csv_path)
        if not rows:
            msg = "Profile.csv is empty"
            raise ValueError(msg)

        row = rows[0]
        first = row.get("First Name", "").strip()
        last = row.get("Last Name", "").strip()
        full_name = f"{first} {last}".strip()
        headline = row.get("Headline", "").strip()

        return full_name, headline

    async def parse(self) -> UserProfile:
        """Build a complete UserProfile from GDPR CSVs + LLM domain inference."""
        full_name, headline = self._parse_profile_csv()
        positions = self._parse_positions()
        skills = self._parse_skills()

        current_role, current_company = _find_current_position(positions)
        experience_years = _calculate_experience_years(positions)

        # Single LLM call to infer domain and suggested keywords
        llm_result = await self._provider.infer_profile_domain(
            headline=headline,
            role=current_role,
            skills=skills,
        )

        domain = str(llm_result.get("domain", "Unknown"))
        raw_keywords = llm_result.get("suggested_keywords", [])
        suggested_keywords = list(raw_keywords) if isinstance(raw_keywords, list) else []

        profile = UserProfile(
            full_name=full_name,
            headline=headline,
            current_role=current_role,
            current_company=current_company,
            domain=domain,
            experience_years=experience_years,
            declared_skills=skills,
            experience=positions,
            suggested_keywords=suggested_keywords,
        )

        logger.info(
            "Parsed profile: %s — %s (%s, %d years)",
            profile.full_name,
            profile.current_role,
            profile.domain,
            profile.experience_years,
        )
        return profile
