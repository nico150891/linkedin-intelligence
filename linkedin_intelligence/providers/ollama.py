"""Ollama LLM provider using httpx."""

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


class OllamaProvider:
    """LLM provider backed by a local Ollama instance."""

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "qwen2.5:7b") -> None:
        self._model = model
        self._base_url = base_url
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=120.0,  # Ollama can be slow on first inference
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    async def _generate(self, prompt: str) -> str:
        """Send a generate request and return the response text."""
        payload = {
            "model": self._model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.1},
        }
        resp = await self._client.post("/api/generate", json=payload)
        resp.raise_for_status()
        data: dict[str, object] = resp.json()
        response = data.get("response", "")
        if not isinstance(response, str):
            msg = f"Unexpected Ollama response type: {type(response)}"
            raise ValueError(msg)
        return response

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
        raw = await self._generate(prompt)
        data = self._parse_json(raw)
        return ExtractedSkills.model_validate(data)

    async def extract_recruiter_signals(self, message: str) -> dict[str, list[str]]:
        """Extract roles and skills mentioned in a recruiter message."""
        prompt = RECRUITER_SIGNAL_PROMPT.format(message=message)
        raw = await self._generate(prompt)
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
        return await self._generate(prompt)

    async def infer_profile_domain(
        self, headline: str, role: str, skills: list[str]
    ) -> dict[str, str | list[str]]:
        """Infer professional domain and suggest search keywords."""
        prompt = PROFILE_PROMPT.format(
            headline=headline,
            current_role=role,
            skills=", ".join(skills),
        )
        raw = await self._generate(prompt)
        data = self._parse_json(raw)
        domain = data.get("domain", "unknown")
        keywords = data.get("suggested_keywords", [])
        return {
            "domain": domain if isinstance(domain, str) else "unknown",
            "suggested_keywords": keywords if isinstance(keywords, list) else [],
        }

    async def health_check(self) -> bool:
        """Verify that Ollama is running and the model is available."""
        try:
            resp = await self._client.get("/api/tags")
            resp.raise_for_status()
        except httpx.HTTPError:
            logger.error("Ollama health check failed — is Ollama running? Try: make ollama-up")
            return False
        return True
