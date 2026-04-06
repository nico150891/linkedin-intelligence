"""LLM provider protocol, shared models, and prompt constants."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, model_validator

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class ExtractedSkills(BaseModel):
    """Structured skills extracted from a job description by an LLM."""

    skills_tecnicas: list[str]
    skills_blandas: list[str]
    tecnologias: list[str]
    industria: str
    seniority: str  # "junior" | "mid" | "senior" | "unknown"
    remote: bool

    @model_validator(mode="before")
    @classmethod
    def normalize(cls, v: dict[str, object]) -> dict[str, object]:
        """Sanitize None lists, strings instead of lists, etc."""
        for key in ("skills_tecnicas", "skills_blandas", "tecnologias"):
            val = v.get(key)
            if val is None:
                v[key] = []
            elif isinstance(val, str):
                v[key] = [val]
        if v.get("seniority") is None:
            v["seniority"] = "unknown"
        if v.get("industria") is None:
            v["industria"] = "unknown"
        if v.get("remote") is None:
            v["remote"] = False
        return v


class WorkExperience(BaseModel):
    """A single work experience entry from the GDPR export."""

    title: str
    company: str
    started_on: str  # ISO date
    finished_on: str | None  # None = current position


class UserProfile(BaseModel):
    """User profile built from the GDPR export."""

    full_name: str
    headline: str
    current_role: str
    current_company: str | None
    domain: str  # inferred by LLM: "AI/ML" | "Data" | "Backend" | etc.
    experience_years: int
    declared_skills: list[str]
    experience: list[WorkExperience]
    suggested_keywords: list[str]


# ---------------------------------------------------------------------------
# Dataclasses for market statistics
# ---------------------------------------------------------------------------


@dataclass
class SkillCount:
    """A skill/technology with its occurrence count."""

    name: str
    count: int


@dataclass
class IndustryCount:
    """An industry with its occurrence count."""

    name: str
    count: int


@dataclass
class MarketStats:
    """Aggregated market statistics from jobs and recruiter messages."""

    # From scraped jobs
    top_tecnologias: list[SkillCount] = field(default_factory=list)
    top_skills_tecnicas: list[SkillCount] = field(default_factory=list)
    top_industrias: list[IndustryCount] = field(default_factory=list)
    seniority_distribution: dict[str, float] = field(default_factory=dict)
    remote_pct: float = 0.0

    # From recruiter messages
    recruiter_mentioned_roles: list[SkillCount] = field(default_factory=list)
    recruiter_mentioned_skills: list[SkillCount] = field(default_factory=list)
    inbound_recruiter_count: int = 0
    top_recruiter_industries: list[IndustryCount] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Prompt constants
# ---------------------------------------------------------------------------

EXTRACTION_PROMPT: str = """\
Analiza la siguiente oferta de empleo y extrae información estructurada.
Responde SOLO con JSON válido, sin texto adicional:

{{
  "skills_tecnicas": ["lista de skills técnicas mencionadas"],
  "skills_blandas": ["lista de skills blandas/soft skills"],
  "tecnologias": ["lista de tecnologías, frameworks, herramientas"],
  "industria": "sector/industria de la empresa",
  "seniority": "junior | mid | senior | unknown",
  "remote": true/false
}}

Oferta:
{job_description}
"""

PORTFOLIO_PROMPT: str = """\
Dado el siguiente perfil profesional y las estadísticas del mercado laboral,
sugiere proyectos de portafolio ordenados por impacto en empleabilidad.
Responde en Markdown.

Perfil:
- Rol actual: {current_role}
- Dominio: {domain}
- Años de experiencia: {experience_years}
- Skills declaradas: {declared_skills}

Top tecnologías en el mercado (de {total_jobs} ofertas analizadas):
{top_tecnologias}

Top skills técnicas:
{top_skills}

Industrias predominantes:
{top_industrias}

Para cada proyecto sugerido incluye: nombre, descripción, stack, por qué es relevante
para este perfil específico, dificultad estimada, y tiempo aproximado.
"""

PROFILE_PROMPT: str = """\
Dado este perfil profesional, responde SOLO con JSON:
{{
  "domain": "string (ej: AI/ML, Data Engineering, Backend, BI, DevOps...)",
  "suggested_keywords": ["lista de 5-8 búsquedas de LinkedIn relevantes para este perfil"]
}}

Headline: {headline}
Cargo actual: {current_role}
Skills declaradas: {skills}
"""

RECRUITER_SIGNAL_PROMPT: str = """\
Analiza este mensaje de un reclutador y extrae información estructurada.
Responde SOLO con JSON válido:

{{
  "roles": ["roles mencionados en el mensaje"],
  "skills": ["skills o tecnologías mencionadas"]
}}

Mensaje:
{message}
"""


# ---------------------------------------------------------------------------
# Provider protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class LLMProvider(Protocol):
    """Contract that all LLM providers must satisfy."""

    async def extract_skills(self, job_description: str) -> ExtractedSkills: ...

    async def extract_recruiter_signals(self, message: str) -> dict[str, list[str]]: ...

    async def suggest_portfolio(self, stats: MarketStats, profile: UserProfile) -> str: ...

    async def infer_profile_domain(
        self, headline: str, role: str, skills: list[str]
    ) -> dict[str, str | list[str]]: ...

    async def health_check(self) -> bool: ...
