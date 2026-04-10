"""LinkedIn jobs scraper with centralized selectors and URL deduplication."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from urllib.parse import quote_plus

from selectolax.parser import HTMLParser

if TYPE_CHECKING:
    from pathlib import Path

    from linkedin_intelligence.scrapers.base import AsyncScraper

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Centralized CSS selectors
# ---------------------------------------------------------------------------


class _Selectors:
    """All LinkedIn CSS selectors in one place.

    LinkedIn serves different HTML for public (logged-out) and authenticated
    (logged-in) views. We try the authenticated selectors first, then fall back
    to the public ones.
    """

    # Authenticated (logged-in) view
    AUTH_JOB_CARD = "li.scaffold-layout__list-item"
    AUTH_JOB_CARD_TITLE = "a.job-card-container__link strong"
    AUTH_JOB_CARD_COMPANY = ".artdeco-entity-lockup__subtitle span"
    AUTH_JOB_CARD_LOCATION = ".artdeco-entity-lockup__caption span"
    AUTH_JOB_CARD_LINK = 'a[href*="/jobs/view/"]'

    # Public (logged-out) view
    PUB_JOB_CARD = "div.job-search-card"
    PUB_JOB_CARD_TITLE = "h3.base-search-card__title"
    PUB_JOB_CARD_COMPANY = "h4.base-search-card__subtitle a"
    PUB_JOB_CARD_LOCATION = "span.job-search-card__location"
    PUB_JOB_CARD_LINK = "a.base-card__full-link"

    # Job detail page (shared between views)
    JOB_DETAIL_DESCRIPTION = "div.description__text"
    JOB_DETAIL_DESCRIPTION_AUTH = "article.jobs-description__container"
    JOB_DETAIL_CRITERIA = "li.description__job-criteria-item"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class ScrapedJob:
    """A single scraped job posting."""

    id: str
    title: str
    company: str
    location: str
    remote: bool
    url: str
    description: str
    scraped_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


# ---------------------------------------------------------------------------
# Scraper
# ---------------------------------------------------------------------------


class JobsScraper:
    """Scrape LinkedIn job listings with deduplication."""

    def __init__(
        self,
        scraper: AsyncScraper,
        output_path: Path,
        max_per_keyword: int = 50,
        since: str | None = None,
    ) -> None:
        self._scraper = scraper
        self._output_path = output_path
        self._max_per_keyword = max_per_keyword
        self._since = since
        self._seen_urls: set[str] = self._load_seen_urls()

    def _load_seen_urls(self) -> set[str]:
        """Load already-scraped job URLs from existing JSONL files."""
        seen: set[str] = set()
        if not self._output_path.exists():
            return seen
        for jsonl_file in self._output_path.glob("*.jsonl"):
            with jsonl_file.open() as f:
                for line in f:
                    try:
                        record = json.loads(line)
                        url = record.get("url", "")
                        if url:
                            seen.add(url)
                    except json.JSONDecodeError:
                        continue
        logger.info("Loaded %d previously scraped URLs", len(seen))
        return seen

    def _build_search_url(self, keyword: str, location: str, start: int = 0) -> str:
        """Build a LinkedIn job search URL."""
        base = "https://www.linkedin.com/jobs/search/"
        params = f"?keywords={quote_plus(keyword)}&location={quote_plus(location)}&start={start}"
        if self._since:
            params += f"&f_TPR=r{self._days_since()}"
        return base + params

    def _days_since(self) -> int:
        """Calculate seconds since --since date for LinkedIn's time filter."""
        if not self._since:
            return 0
        since_dt = datetime.strptime(self._since, "%Y-%m-%d").replace(  # noqa: DTZ007
            tzinfo=UTC,
        )
        delta = datetime.now(UTC) - since_dt
        return max(1, int(delta.total_seconds()))

    def _parse_job_cards(self, html: str) -> list[dict[str, str]]:
        """Extract job card metadata from search results HTML."""
        tree = HTMLParser(html)
        cards: list[dict[str, str]] = []

        # Try authenticated selectors first, fall back to public
        nodes = tree.css(_Selectors.AUTH_JOB_CARD)
        if nodes:
            sel_title = _Selectors.AUTH_JOB_CARD_TITLE
            sel_company = _Selectors.AUTH_JOB_CARD_COMPANY
            sel_location = _Selectors.AUTH_JOB_CARD_LOCATION
            sel_link = _Selectors.AUTH_JOB_CARD_LINK
        else:
            nodes = tree.css(_Selectors.PUB_JOB_CARD)
            sel_title = _Selectors.PUB_JOB_CARD_TITLE
            sel_company = _Selectors.PUB_JOB_CARD_COMPANY
            sel_location = _Selectors.PUB_JOB_CARD_LOCATION
            sel_link = _Selectors.PUB_JOB_CARD_LINK

        for node in nodes:
            title_el = node.css_first(sel_title)
            company_el = node.css_first(sel_company)
            location_el = node.css_first(sel_location)
            link_el = node.css_first(sel_link)

            if not title_el or not link_el:
                continue

            raw_href = link_el.attributes.get("href") or ""
            url = raw_href.split("?")[0]
            if url.startswith("/"):
                url = "https://www.linkedin.com" + url
            if url in self._seen_urls:
                continue

            cards.append(
                {
                    "title": title_el.text(strip=True),
                    "company": company_el.text(strip=True) if company_el else "Unknown",
                    "location": location_el.text(strip=True) if location_el else "Unknown",
                    "url": url,
                }
            )

        return cards

    def _parse_job_detail(self, html: str) -> str:
        """Extract job description text from detail page HTML."""
        tree = HTMLParser(html)
        desc_el = tree.css_first(_Selectors.JOB_DETAIL_DESCRIPTION)
        if desc_el is None:
            desc_el = tree.css_first(_Selectors.JOB_DETAIL_DESCRIPTION_AUTH)
        if desc_el is None:
            return ""
        return desc_el.text(strip=True)

    @staticmethod
    def _detect_remote(title: str, location: str, description: str) -> bool:
        """Heuristic remote detection from job text."""
        combined = f"{title} {location} {description}".lower()
        return bool(re.search(r"\b(remote|remoto|teletrabajo|work from home)\b", combined))

    @staticmethod
    def _generate_id(url: str) -> str:
        """Extract a stable ID from a LinkedIn job URL."""
        match = re.search(r"/view/[^/]+-(\d+)", url)
        if match:
            return match.group(1)
        return url.rstrip("/").split("/")[-1]

    async def scrape_keyword(
        self,
        keyword: str,
        location: str,
        dry_run: bool = False,
    ) -> list[ScrapedJob]:
        """Scrape jobs for a single keyword+location pair."""
        jobs: list[ScrapedJob] = []
        start = 0

        while len(jobs) < self._max_per_keyword:
            url = self._build_search_url(keyword, location, start)

            if dry_run:
                logger.info("[DRY RUN] Would fetch: %s", url)
                break

            await self._scraper._navigate(url)
            await self._scraper.delay()

            html = await self._scraper.page.content()
            cards = self._parse_job_cards(html)

            if not cards:
                logger.debug("No job cards found at start=%d. URL: %s", start, url)
                # Save HTML for debugging selector issues
                debug_path = self._output_path / "_debug_search.html"
                debug_path.parent.mkdir(parents=True, exist_ok=True)
                debug_path.write_text(html)
                logger.debug("Saved debug HTML to %s", debug_path)
                break

            for card in cards:
                if len(jobs) >= self._max_per_keyword:
                    break
                if card["url"] in self._seen_urls:
                    continue

                await self._scraper._navigate(card["url"])
                await self._scraper.delay()

                detail_html = await self._scraper.page.content()
                description = self._parse_job_detail(detail_html)

                if len(description) < 100:
                    logger.debug("Skipping job with short description: %s", card["url"])
                    continue

                job = ScrapedJob(
                    id=self._generate_id(card["url"]),
                    title=card["title"],
                    company=card["company"],
                    location=card["location"],
                    remote=self._detect_remote(card["title"], card["location"], description),
                    url=card["url"],
                    description=description,
                )
                jobs.append(job)
                self._seen_urls.add(card["url"])

            start += 25  # LinkedIn pagination step

        logger.info("Scraped %d jobs for keyword '%s'", len(jobs), keyword)
        return jobs

    def save_jobs(self, jobs: list[ScrapedJob], keyword: str) -> None:
        """Append scraped jobs to a JSONL file (one per keyword)."""
        self._output_path.mkdir(parents=True, exist_ok=True)
        safe_keyword = re.sub(r"[^\w\-]", "_", keyword.lower())
        out_file = self._output_path / f"jobs_{safe_keyword}.jsonl"

        with out_file.open("a") as f:
            for job in jobs:
                line = json.dumps(
                    {
                        "id": job.id,
                        "title": job.title,
                        "company": job.company,
                        "location": job.location,
                        "remote": job.remote,
                        "url": job.url,
                        "description": job.description,
                        "scraped_at": job.scraped_at,
                    },
                    ensure_ascii=False,
                )
                f.write(line + "\n")

        logger.info("Saved %d jobs to %s", len(jobs), out_file)
