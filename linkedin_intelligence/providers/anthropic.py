"""Anthropic LLM provider using the official SDK."""

from __future__ import annotations

import json
import logging

import anthropic
from tenacity import retry, stop_after_attempt, wait_exponential

from linkedin_intelligence.providers.base import (
    EXTRACTION_PROMPT,
    PORTFOLIO_PROMPT,
    PROFILE_PROMPT,
    RECRUITER_SIGNAL_PROMPT,
    ExtractedSkills,
    MarketStats,
    UserProfile,
)

logger = logging.getLogger(__name__)


class AnthropicProvider:
    """LLM provider backed by the Anthropic Messages API."""

    def __init__(self, api_key: str, model: str = "claude-opus-4-5") -> None:
        self._model = model
        self._client = anthropic.AsyncAnthropic(api_key=api_key)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    async def _chat(self, prompt: str, max_tokens: int = 4096) -> str:
        """Send a message and return the assistant text."""
        message = await self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        block = message.content[0]
        if block.type != "text":
            msg = f"Unexpected block type: {block.type}"
            raise ValueError(msg)
        return block.text

    def _parse_json(self, text: str) -> dict[str, object]:
        """Extract JSON from an LLM response that may contain markdown fences."""
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines)
        result: dict[str, object] = json.loads(cleaned)
        return result

    # ------------------------------------------------------------------
    # Protocol implementation
    # ------------------------------------------------------------------

    async def extract_skills(self, job_description: str) -> ExtractedSkills:
        """Extract structured skills from a job description."""
        prompt = EXTRACTION_PROMPT.format(job_description=job_description)
        raw = await self._chat(prompt)
        data = self._parse_json(raw)
        return ExtractedSkills.model_validate(data)

    async def extract_recruiter_signals(self, message: str) -> dict[str, list[str]]:
        """Extract roles and skills mentioned in a recruiter message."""
        prompt = RECRUITER_SIGNAL_PROMPT.format(message=message)
        raw = await self._chat(prompt)
        data = self._parse_json(raw)
        roles = data.get("roles", [])
        skills = data.get("skills", [])
        return {
            "roles": roles if isinstance(roles, list) else [],
            "skills": skills if isinstance(skills, list) else [],
        }

    async def suggest_portfolio(self, stats: MarketStats, profile: UserProfile) -> str:
        """Generate portfolio project suggestions based on market stats and profile."""
        prompt = PORTFOLIO_PROMPT.format(
            current_role=profile.current_role,
            domain=profile.domain,
            experience_years=profile.experience_years,
            declared_skills=", ".join(profile.declared_skills),
            total_jobs=sum(s.count for s in stats.top_tecnologias),
            top_tecnologias="\n".join(f"- {s.name}: {s.count}" for s in stats.top_tecnologias[:10]),
            top_skills="\n".join(f"- {s.name}: {s.count}" for s in stats.top_skills_tecnicas[:10]),
            top_industrias="\n".join(f"- {i.name}: {i.count}" for i in stats.top_industrias[:10]),
        )
        return await self._chat(prompt)

    async def infer_profile_domain(
        self, headline: str, role: str, skills: list[str]
    ) -> dict[str, str | list[str]]:
        """Infer professional domain and suggest search keywords."""
        prompt = PROFILE_PROMPT.format(
            headline=headline,
            current_role=role,
            skills=", ".join(skills),
        )
        raw = await self._chat(prompt)
        data = self._parse_json(raw)
        domain = data.get("domain", "unknown")
        keywords = data.get("suggested_keywords", [])
        return {
            "domain": domain if isinstance(domain, str) else "unknown",
            "suggested_keywords": keywords if isinstance(keywords, list) else [],
        }

    async def health_check(self) -> bool:
        """Verify connectivity to the Anthropic API."""
        try:
            await self._client.messages.create(
                model=self._model,
                max_tokens=5,
                messages=[{"role": "user", "content": "ping"}],
            )
        except anthropic.APIError:
            logger.exception("Anthropic health check failed")
            return False
        return True
