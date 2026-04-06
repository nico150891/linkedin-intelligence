"""GDPR export parser — messages, connections, and job applications."""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from datetime import datetime
from io import StringIO
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)

# Keywords that signal a recruiter message (case-insensitive check)
_RECRUITER_KEYWORDS: tuple[str, ...] = (
    "opportunity",
    "oportunidad",
    "position",
    "posición",
    "role",
    "recruiting",
    "recruiter",
    "encajarías",
    "interested in chatting",
    "open to",
    "would you be",
    "shall i share",
    "would this interest",
    "exploring this opportunity",
)


@dataclass
class Message:
    """A single LinkedIn direct message."""

    sender: str
    recipient: str
    date: datetime
    subject: str
    content: str
    is_recruiter: bool


@dataclass
class Connection:
    """A LinkedIn connection."""

    first_name: str
    last_name: str
    email: str
    company: str
    position: str
    connected_on: datetime


@dataclass
class JobApplication:
    """A LinkedIn job application."""

    application_date: datetime
    company: str
    job_title: str
    status: str


def _strip_bom(text: str) -> str:
    """Remove UTF-8 BOM if present."""
    return text.lstrip("\ufeff")


def _read_csv(path: Path) -> list[dict[str, str]]:
    """Read a CSV file handling BOM and returning a list of row dicts."""
    raw = path.read_text(encoding="utf-8-sig")
    raw = _strip_bom(raw)
    reader = csv.DictReader(StringIO(raw))
    return list(reader)


def _parse_date_flexible(value: str) -> datetime:
    """Parse dates in multiple formats found in GDPR exports."""
    value = value.strip()
    # Try ISO-like format first: "2024-01-20 10:30:00" or "2024-01-20"
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%d %b %Y",  # "15 Jan 2024"
        "%b %Y",  # "Jan 2022"
    ):
        try:
            return datetime.strptime(value, fmt)  # noqa: DTZ007
        except ValueError:
            continue
    msg = f"Unable to parse date: {value!r}"
    raise ValueError(msg)


def _is_recruiter_message(sender: str, user_name: str, subject: str, content: str) -> bool:
    """Heuristic: sender is not the user + keywords in subject/content."""
    if sender.strip().lower() == user_name.strip().lower():
        return False
    combined = f"{subject} {content}".lower()
    return any(kw in combined for kw in _RECRUITER_KEYWORDS)


class GDPRParser:
    """Parse LinkedIn GDPR export CSVs into structured data."""

    def __init__(self, gdpr_path: Path, user_name: str = "") -> None:
        self._path = gdpr_path
        self._user_name = user_name

    def parse_messages(self) -> list[Message]:
        """Parse messages.csv with deduplication and recruiter detection."""
        csv_path = self._path / "messages.csv"
        if not csv_path.exists():
            logger.warning("messages.csv not found at %s", csv_path)
            return []

        rows = _read_csv(csv_path)
        seen: set[tuple[str, str, str]] = set()
        messages: list[Message] = []

        for row in rows:
            sender = row.get("From", "").strip()
            recipient = row.get("To", "").strip()
            date_str = row.get("Date", "").strip()
            subject = row.get("Subject", "").strip()
            content = row.get("Content", "").strip()

            if not sender or not date_str:
                continue

            # Dedup key: sender + date + subject
            dedup_key = (sender, date_str, subject)
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            date = _parse_date_flexible(date_str)
            is_recruiter = _is_recruiter_message(sender, self._user_name, subject, content)

            messages.append(
                Message(
                    sender=sender,
                    recipient=recipient,
                    date=date,
                    subject=subject,
                    content=content,
                    is_recruiter=is_recruiter,
                )
            )

        logger.info(
            "Parsed %d messages (%d from recruiters)",
            len(messages),
            sum(1 for m in messages if m.is_recruiter),
        )
        return messages

    def parse_connections(self) -> list[Connection]:
        """Parse connections.csv."""
        csv_path = self._path / "connections.csv"
        if not csv_path.exists():
            logger.warning("connections.csv not found at %s", csv_path)
            return []

        rows = _read_csv(csv_path)
        seen: set[str] = set()
        connections: list[Connection] = []

        for row in rows:
            email = row.get("Email Address", "").strip()
            first = row.get("First Name", "").strip()
            last = row.get("Last Name", "").strip()

            # Dedup by email
            dedup_key = email or f"{first}_{last}"
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            connected_str = row.get("Connected On", "").strip()
            if not connected_str:
                continue

            connections.append(
                Connection(
                    first_name=first,
                    last_name=last,
                    email=email,
                    company=row.get("Company", "").strip(),
                    position=row.get("Position", "").strip(),
                    connected_on=_parse_date_flexible(connected_str),
                )
            )

        logger.info("Parsed %d connections", len(connections))
        return connections

    def parse_job_applications(self) -> list[JobApplication]:
        """Parse job_applications.csv."""
        csv_path = self._path / "job_applications.csv"
        if not csv_path.exists():
            logger.warning("job_applications.csv not found at %s", csv_path)
            return []

        rows = _read_csv(csv_path)
        seen: set[tuple[str, str]] = set()
        applications: list[JobApplication] = []

        for row in rows:
            date_str = row.get("Application Date", "").strip()
            company = row.get("Company Name", "").strip()
            title = row.get("Job Title", "").strip()
            status = row.get("Application Status", "").strip()

            if not date_str or not company:
                continue

            # Dedup by company + title
            dedup_key = (company, title)
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            applications.append(
                JobApplication(
                    application_date=_parse_date_flexible(date_str),
                    company=company,
                    job_title=title,
                    status=status,
                )
            )

        logger.info("Parsed %d job applications", len(applications))
        return applications
