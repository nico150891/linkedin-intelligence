"""CLI entry point for linkedin-intel."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from linkedin_intelligence.config import _setup_logging, get_settings

app = typer.Typer(
    name="linkedin-intel",
    help="Analyze the job market from LinkedIn using scraping, GDPR exports, and LLMs.",
)
console = Console()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _show_profile_summary(profile: object) -> None:
    """Display a rich table with the detected UserProfile."""
    from linkedin_intelligence.providers.base import UserProfile

    if not isinstance(profile, UserProfile):
        return

    table = Table(title="Detected Profile", show_header=False)
    table.add_column("Field", style="bold cyan")
    table.add_column("Value")

    table.add_row("Name", profile.full_name)
    table.add_row("Headline", profile.headline)
    table.add_row("Current role", profile.current_role)
    table.add_row("Company", profile.current_company or "N/A")
    table.add_row("Domain", profile.domain)
    table.add_row("Experience", f"{profile.experience_years} years")
    table.add_row("Skills", ", ".join(profile.declared_skills[:10]))
    table.add_row("Keywords", ", ".join(profile.suggested_keywords))

    console.print(table)


def _show_stats_summary(stats: object) -> None:
    """Display a rich summary of MarketStats."""
    from linkedin_intelligence.providers.base import MarketStats

    if not isinstance(stats, MarketStats):
        return

    console.print("\n[bold]Market Statistics[/bold]")

    if stats.top_tecnologias:
        table = Table(title="Top Technologies")
        table.add_column("Technology", style="cyan")
        table.add_column("Count", justify="right")
        for item in stats.top_tecnologias[:10]:
            table.add_row(item.name, str(item.count))
        console.print(table)

    if stats.top_skills_tecnicas:
        table = Table(title="Top Technical Skills")
        table.add_column("Skill", style="green")
        table.add_column("Count", justify="right")
        for item in stats.top_skills_tecnicas[:10]:
            table.add_row(item.name, str(item.count))
        console.print(table)

    if stats.top_industrias:
        table = Table(title="Top Industries")
        table.add_column("Industry", style="yellow")
        table.add_column("Count", justify="right")
        for ind in stats.top_industrias[:10]:
            table.add_row(ind.name, str(ind.count))
        console.print(table)

    if stats.seniority_distribution:
        table = Table(title="Seniority Distribution")
        table.add_column("Level", style="magenta")
        table.add_column("Percentage", justify="right")
        for level, pct in stats.seniority_distribution.items():
            table.add_row(level, f"{pct}%")
        console.print(table)

    console.print(f"\nRemote: [bold]{stats.remote_pct}%[/bold]")

    if stats.inbound_recruiter_count > 0:
        console.print(f"Recruiter messages analyzed: [bold]{stats.inbound_recruiter_count}[/bold]")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@app.command()
def test_provider() -> None:
    """Health check for the active LLM provider."""
    settings = get_settings()
    _setup_logging(settings)

    from linkedin_intelligence.providers import get_provider

    provider = get_provider(settings)
    ok = asyncio.run(provider.health_check())

    if ok:
        console.print(f"[green]Provider '{settings.llm_provider}' is healthy.[/green]")
    else:
        console.print(f"[red]Provider '{settings.llm_provider}' health check failed.[/red]")
        raise typer.Exit(1)


@app.command()
def parse_profile() -> None:
    """Detect UserProfile from the GDPR export."""
    settings = get_settings()
    _setup_logging(settings)

    from linkedin_intelligence.parsers.profile import ProfileParser
    from linkedin_intelligence.providers import get_provider

    provider = get_provider(settings)
    parser = ProfileParser(settings.gdpr_export_path, provider)
    profile = asyncio.run(parser.parse())
    _show_profile_summary(profile)


@app.command()
def parse_gdpr() -> None:
    """Parse GDPR export: messages, connections, job applications."""
    settings = get_settings()
    _setup_logging(settings)

    from linkedin_intelligence.parsers.gdpr import GDPRParser

    parser = GDPRParser(settings.gdpr_export_path)
    messages = parser.parse_messages()
    connections = parser.parse_connections()
    applications = parser.parse_job_applications()

    console.print(f"Messages: [bold]{len(messages)}[/bold]")
    console.print(f"Connections: [bold]{len(connections)}[/bold]")
    console.print(f"Applications: [bold]{len(applications)}[/bold]")

    recruiter_msgs = [m for m in messages if m.is_recruiter]
    console.print(f"Recruiter messages: [bold]{len(recruiter_msgs)}[/bold]")


@app.command()
def scrape_jobs(
    keywords: Annotated[list[str] | None, typer.Option(help="Search keywords")] = None,
    location: Annotated[str, typer.Option(help="Job location filter")] = "Spain",
    since: Annotated[str | None, typer.Option(help="Only jobs after YYYY-MM-DD")] = None,
    dry_run: Annotated[bool, typer.Option(help="Simulate without making requests")] = False,
    headed: Annotated[bool, typer.Option(help="Show browser window (for CAPTCHA solving)")] = False,
) -> None:
    """Scrape LinkedIn job listings."""
    settings = get_settings()
    _setup_logging(settings)

    if not keywords:
        console.print(
            "[yellow]No --keywords provided. Use parse-profile first or pass --keywords.[/yellow]"
        )
        raise typer.Exit(1)

    async def _run() -> None:
        from linkedin_intelligence.scrapers.base import AsyncScraper
        from linkedin_intelligence.scrapers.jobs import JobsScraper

        session_path = settings.gdpr_export_path.parent / ".session"
        scraper = AsyncScraper(
            session_path=session_path,
            delay=settings.scrape_delay_seconds,
            headless=not headed,
        )
        await scraper.start()

        try:
            if not dry_run:
                await scraper.login(
                    settings.linkedin_email,
                    settings.linkedin_password.get_secret_value(),
                )

            jobs_scraper = JobsScraper(
                scraper=scraper,
                output_path=settings.jobs_output_path,
                max_per_keyword=settings.max_jobs_per_keyword,
                since=since,
            )

            for kw in keywords or []:
                jobs = await jobs_scraper.scrape_keyword(kw, location, dry_run=dry_run)
                if jobs:
                    jobs_scraper.save_jobs(jobs, kw)
        finally:
            await scraper.stop()

    asyncio.run(_run())


@app.command()
def extract_skills() -> None:
    """Extract skills from scraped jobs (incremental, cached)."""
    settings = get_settings()
    _setup_logging(settings)

    from linkedin_intelligence.extractors.skills import SkillsExtractor
    from linkedin_intelligence.providers import get_provider

    provider = get_provider(settings)
    extractor = SkillsExtractor(provider, settings.processed_path)
    count = asyncio.run(extractor.extract_batch(settings.jobs_output_path))
    console.print(f"Extracted skills for [bold]{count}[/bold] new jobs.")


@app.command()
def analyze() -> None:
    """Compute market statistics and show summary."""
    settings = get_settings()
    _setup_logging(settings)

    from linkedin_intelligence.analysis.stats import compute_stats

    enriched_path = settings.processed_path / "jobs_enriched.jsonl"
    signals_path = settings.processed_path / "recruiter_signals.jsonl"

    stats = compute_stats(
        enriched_path,
        recruiter_signals_path=signals_path if signals_path.exists() else None,
    )
    _show_stats_summary(stats)


@app.command()
def run_all(
    keywords: Annotated[list[str] | None, typer.Option(help="Search keywords")] = None,
    location: Annotated[str, typer.Option(help="Job location filter")] = "Spain",
) -> None:
    """Run the full pipeline: profile -> gdpr -> scrape -> extract -> analyze."""
    settings = get_settings()
    _setup_logging(settings)

    from linkedin_intelligence.analysis.portfolio import generate_portfolio_suggestions
    from linkedin_intelligence.analysis.stats import compute_stats
    from linkedin_intelligence.extractors.skills import SkillsExtractor
    from linkedin_intelligence.parsers.gdpr import GDPRParser
    from linkedin_intelligence.parsers.profile import ProfileParser
    from linkedin_intelligence.providers import get_provider

    provider = get_provider(settings)

    async def _run() -> None:
        # 1. Parse profile
        console.print("\n[bold]Step 1/5: Parsing profile...[/bold]")
        profile = None
        try:
            parser = ProfileParser(settings.gdpr_export_path, provider)
            profile = await parser.parse()
            _show_profile_summary(profile)
        except FileNotFoundError:
            console.print("[yellow]GDPR export not found — continuing without profile.[/yellow]")

        # 2. Parse GDPR
        console.print("\n[bold]Step 2/5: Parsing GDPR data...[/bold]")
        gdpr = GDPRParser(
            settings.gdpr_export_path,
            user_name=profile.full_name if profile else "",
        )
        messages = gdpr.parse_messages()
        connections = gdpr.parse_connections()
        applications = gdpr.parse_job_applications()
        console.print(
            f"  Messages: {len(messages)}, Connections: {len(connections)}, "
            f"Applications: {len(applications)}"
        )

        # 3. Scrape jobs
        search_keywords = keywords
        if not search_keywords and profile:
            search_keywords = profile.suggested_keywords
        if not search_keywords:
            console.print("[yellow]No keywords — skipping scrape.[/yellow]")
        else:
            console.print(f"\n[bold]Step 3/5: Scraping jobs for {search_keywords}...[/bold]")
            from linkedin_intelligence.scrapers.base import AsyncScraper
            from linkedin_intelligence.scrapers.jobs import JobsScraper

            session_path = settings.gdpr_export_path.parent / ".session"
            scraper = AsyncScraper(
                session_path=session_path,
                delay=settings.scrape_delay_seconds,
            )
            await scraper.start()
            try:
                await scraper.login(
                    settings.linkedin_email,
                    settings.linkedin_password.get_secret_value(),
                )
                jobs_scraper = JobsScraper(
                    scraper=scraper,
                    output_path=settings.jobs_output_path,
                    max_per_keyword=settings.max_jobs_per_keyword,
                )
                for kw in search_keywords:
                    scraped = await jobs_scraper.scrape_keyword(kw, location)
                    if scraped:
                        jobs_scraper.save_jobs(scraped, kw)
            finally:
                await scraper.stop()

        # 4. Extract skills
        console.print("\n[bold]Step 4/5: Extracting skills...[/bold]")
        extractor = SkillsExtractor(provider, settings.processed_path)
        count = await extractor.extract_batch(settings.jobs_output_path)
        console.print(f"  Extracted skills for {count} new jobs.")

        # 5. Analyze
        console.print("\n[bold]Step 5/5: Analyzing market...[/bold]")
        enriched_path = settings.processed_path / "jobs_enriched.jsonl"
        stats = compute_stats(enriched_path)
        _show_stats_summary(stats)

        # Portfolio suggestions
        if profile:
            console.print("\n[bold]Generating portfolio suggestions...[/bold]")
            suggestions = await generate_portfolio_suggestions(provider, stats, profile)
            console.print(suggestions)

            output_path = Path("output/portfolio_suggestions.md")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(suggestions)
            console.print(f"\nSaved to [bold]{output_path}[/bold]")

    asyncio.run(_run())


@app.command()
def sample_run() -> None:
    """Run the pipeline with synthetic data from data/sample/ (no credentials needed)."""
    sample_gdpr = Path("data/sample/gdpr")
    sample_jobs = Path("data/sample/jobs_sample.jsonl")

    if not sample_gdpr.exists() or not sample_jobs.exists():
        console.print("[red]Sample data not found in data/sample/[/red]")
        raise typer.Exit(1)

    console.print("[bold]Running pipeline with sample data...[/bold]\n")

    # 1. Parse profile (no LLM needed — build directly from CSVs)
    console.print("[bold]Step 1: Parsing profile...[/bold]")
    from linkedin_intelligence.parsers.gdpr import _parse_date_flexible, _read_csv
    from linkedin_intelligence.providers.base import UserProfile, WorkExperience

    profile_rows = _read_csv(sample_gdpr / "Profile.csv")
    row = profile_rows[0]
    full_name = f"{row.get('First Name', '')} {row.get('Last Name', '')}".strip()
    headline = row.get("Headline", "")

    position_rows = _read_csv(sample_gdpr / "Positions.csv")
    positions: list[WorkExperience] = []
    for pos_row in position_rows:
        title = pos_row.get("Title", "").strip()
        company = pos_row.get("Company Name", "").strip()
        started = pos_row.get("Started On", "").strip()
        finished = pos_row.get("Finished On", "").strip() or None
        if not title or not started:
            continue
        try:
            started_iso = _parse_date_flexible(started).strftime("%Y-%m-%d")
        except ValueError:
            continue
        finished_iso = None
        if finished:
            with contextlib.suppress(ValueError):
                finished_iso = _parse_date_flexible(finished).strftime("%Y-%m-%d")
        positions.append(
            WorkExperience(
                title=title, company=company, started_on=started_iso, finished_on=finished_iso
            )
        )

    skills_rows = _read_csv(sample_gdpr / "Skills.csv")
    declared_skills = [r["Name"].strip() for r in skills_rows if r.get("Name", "").strip()]

    current_role = "Unknown"
    current_company: str | None = None
    for pos in positions:
        if pos.finished_on is None:
            current_role = pos.title
            current_company = pos.company
            break

    profile = UserProfile(
        full_name=full_name,
        headline=headline,
        current_role=current_role,
        current_company=current_company,
        domain="AI/ML",
        experience_years=max(1, 2026 - 2014),
        declared_skills=declared_skills,
        experience=positions,
        suggested_keywords=["ML engineer", "AI researcher", "data scientist"],
    )
    _show_profile_summary(profile)

    # 2. Parse GDPR
    console.print("\n[bold]Step 2: Parsing GDPR data...[/bold]")
    from linkedin_intelligence.parsers.gdpr import GDPRParser

    gdpr = GDPRParser(sample_gdpr, user_name=full_name)
    messages = gdpr.parse_messages()
    connections = gdpr.parse_connections()
    applications = gdpr.parse_job_applications()
    recruiter_msgs = [m for m in messages if m.is_recruiter]

    console.print(f"  Messages: {len(messages)} ({len(recruiter_msgs)} from recruiters)")
    console.print(f"  Connections: {len(connections)}")
    console.print(f"  Applications: {len(applications)}")

    # 3. Stats from pre-enriched sample jobs
    console.print("\n[bold]Step 3: Computing market stats from sample data...[/bold]")
    from linkedin_intelligence.analysis.stats import compute_stats

    stats = compute_stats(sample_jobs)
    _show_stats_summary(stats)

    console.print("\n[bold green]Sample run complete.[/bold green]")
    console.print(
        "To run with real data, configure .env and use: "
        "[bold]linkedin-intel run-all --location Spain[/bold]"
    )


if __name__ == "__main__":
    app()
