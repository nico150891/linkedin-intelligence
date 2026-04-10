"""Base async scraper with login, session persistence, retry, and rate limiting."""

from __future__ import annotations

import asyncio
import logging
import random
from typing import TYPE_CHECKING

from playwright.async_api import async_playwright
from tenacity import retry, stop_after_attempt, wait_exponential

if TYPE_CHECKING:
    from pathlib import Path

    from playwright.async_api import Browser, BrowserContext, Page

logger = logging.getLogger(__name__)


class AsyncScraper:
    """Base scraper with Playwright session, retry, and delay+jitter."""

    def __init__(
        self,
        session_path: Path,
        delay: float = 2.5,
        headless: bool = True,
    ) -> None:
        self._session_path = session_path
        self._delay = delay
        self._headless = headless
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    async def _ensure_session_dir(self) -> None:
        """Create session directory if it doesn't exist."""
        self._session_path.parent.mkdir(parents=True, exist_ok=True)

    async def start(self) -> None:
        """Launch browser and restore session if available."""
        pw = await async_playwright().start()
        self._browser = await pw.chromium.launch(headless=self._headless)

        storage_path = self._session_path
        if storage_path.exists():
            logger.info("Restoring session from %s", storage_path)
            self._context = await self._browser.new_context(storage_state=str(storage_path))
        else:
            self._context = await self._browser.new_context()

        self._page = await self._context.new_page()

    async def stop(self) -> None:
        """Save session and close browser."""
        if self._context is not None:
            await self._save_session()
            await self._context.close()
        if self._browser is not None:
            await self._browser.close()

    async def _save_session(self) -> None:
        """Persist cookies/storage for next run."""
        if self._context is None:
            return
        await self._ensure_session_dir()
        await self._context.storage_state(path=str(self._session_path))
        logger.debug("Session saved to %s", self._session_path)

    @property
    def page(self) -> Page:
        """Return the active page, raising if not started."""
        if self._page is None:
            msg = "Scraper not started — call start() first"
            raise RuntimeError(msg)
        return self._page

    async def delay(self) -> None:
        """Wait with jitter to avoid detection."""
        jitter = random.uniform(0.5, 1.5)  # noqa: S311
        await asyncio.sleep(self._delay * jitter)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=15),
        reraise=True,
    )
    async def _navigate(self, url: str) -> None:
        """Navigate to a URL with retry."""
        await self.page.goto(url, wait_until="domcontentloaded", timeout=30000)

    async def login(self, email: str, password: str) -> None:
        """Log in to LinkedIn if not already authenticated."""
        await self._navigate("https://www.linkedin.com/feed/")
        await asyncio.sleep(2)

        current_url = self.page.url
        if "/feed" in current_url:
            logger.info("Already logged in (session restored)")
            return

        logger.info("Logging in to LinkedIn...")
        await self._navigate("https://www.linkedin.com/login")

        # Wait for login form — LinkedIn may redirect or show a challenge
        try:
            await self.page.wait_for_selector("#username", timeout=15000)
        except Exception:
            logger.warning(
                "Login form not found (page: %s). LinkedIn may require manual verification. "
                "Run with --headed to resolve.",
                self.page.url,
            )
            raise

        await self.page.fill("#username", email)
        await self.page.fill("#password", password)
        await self.page.click('button[type="submit"]')

        # LinkedIn may show a CAPTCHA or verification challenge.
        # If running headed, give the user time to resolve it manually.
        try:
            await self.page.wait_for_url("**/feed/**", timeout=15000)
        except Exception:
            current = self.page.url
            if "checkpoint" in current or "challenge" in current:
                if not self._headless:
                    logger.info(
                        "LinkedIn verification detected. "
                        "Please solve the challenge in the browser. Waiting up to 120s..."
                    )
                    await self.page.wait_for_url("**/feed/**", timeout=120000)
                else:
                    logger.warning(
                        "LinkedIn verification detected (current: %s). "
                        "Run with --headed to solve manually.",
                        current,
                    )
                    raise
            else:
                raise

        await self._save_session()
        logger.info("Login successful")
