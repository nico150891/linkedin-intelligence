"""Portfolio suggestions generator using LLM + UserProfile + MarketStats."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from linkedin_intelligence.providers.base import LLMProvider, MarketStats, UserProfile

logger = logging.getLogger(__name__)


async def generate_portfolio_suggestions(
    provider: LLMProvider,
    stats: MarketStats,
    profile: UserProfile,
) -> str:
    """Call the LLM provider to generate personalized portfolio suggestions.

    Returns:
        Markdown-formatted portfolio suggestions.
    """
    logger.info(
        "Generating portfolio suggestions for %s (%s)",
        profile.full_name,
        profile.domain,
    )
    result = await provider.suggest_portfolio(stats, profile)
    logger.info("Portfolio suggestions generated (%d chars)", len(result))
    return result
