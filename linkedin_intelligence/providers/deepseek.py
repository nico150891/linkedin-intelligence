"""DeepSeek LLM provider using httpx."""

from __future__ import annotations

import json
import logging

import httpx
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

_BASE_URL = "https://api.deepseek.com"


class DeepSeekProvider:
    """LLM provider backed by the DeepSeek chat API."""

    def __init__(self, api_key: str, model: str = "deepseek-chat") -> None:
        self._model = model
        self._client = httpx.AsyncClient(
            base_url=_BASE_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=60.0,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    async def _chat(self, prompt: str) -> str:
        """Send a chat completion request and return the assistant message."""
        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
        }
        resp = await self._client.post("/chat/completions", json=payload)
        resp.raise_for_status()
        data: dict[str, object] = resp.json()
        choices = data.get("choices")
        if not isinstance(choices, list) or len(choices) == 0:
            msg = f"Unexpected DeepSeek response: {data}"
            raise ValueError(msg)
        first = choices[0]
        if not isinstance(first, dict):
            msg = f"Unexpected choice format: {first}"
            raise ValueError(msg)
        message = first.get("message")
        if not isinstance(message, dict):
            msg = f"Unexpected message format: {message}"
            raise ValueError(msg)
        content = message.get("content", "")
        if not isinstance(content, str):
            msg = f"Unexpected content type: {type(content)}"
            raise ValueError(msg)
        return content

    def _parse_json(self, text: str) -> dict[str, object]:
        """Extract JSON from an LLM response that may contain markdown fences."""
        cleaned = text.strip()
        if cleaned.startswith("```"):
            # Remove opening fence (with optional language tag) and closing fence
            lines = cleaned.split("\n")
            lines = lines[1:]  # drop opening ```json
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
        """Verify connectivity to the DeepSeek API."""
        try:
            resp = await self._client.post(
                "/chat/completions",
                json={
                    "model": self._model,
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 5,
                },
            )
            resp.raise_for_status()
        except httpx.HTTPError:
            logger.exception("DeepSeek health check failed")
            return False
        return True
