# CLAUDE.md — linkedin-intelligence

> Fuente de verdad para Claude Code. Leer completo antes de escribir código.
> Ante cualquier duda de implementación, este archivo tiene prioridad sobre intuición.

---

## Contexto del proyecto

Herramienta CLI personal para analizar el mercado laboral desde LinkedIn. Combina scraping,
parseo de exports GDPR y extracción con LLMs para producir estadísticas de skills/industrias
y sugerencias de proyectos de portafolio priorizadas por demanda real de mercado.
Adaptable a cualquier perfil profesional — el sistema detecta el rol del usuario desde
su export GDPR y personaliza keywords y sugerencias en consecuencia.

**Repo:** `https://github.com/nico150891/linkedin-intelligence`
**Autor:** Nicolás Leiva
**Python:** 3.12+

---

## Stack

| Capa | Herramienta | Motivo |
|---|---|---|
| CLI | `typer` | Autocompletion, help automático, testeable |
| Scraping | `playwright` (async) | JS rendering, sesión persistente |
| HTML parsing | `selectolax` | ~10x más rápido que BeautifulSoup |
| HTTP client | `httpx` | Async nativo, usado por todos los LLM providers |
| LLM abstraction | `Protocol` + adaptadores | Intercambiable sin tocar lógica de negocio |
| Modelos de datos | `pydantic v2` | Validación de LLM responses y config |
| Config | `pydantic-settings` | `.env` tipado, validado al arranque |
| Análisis | `pandas` + `collections` | Agregaciones y distribuciones |
| Progress | `rich` | Barras de progreso para runs largos (Ollama) |
| Retry | `tenacity` | Backoff exponencial en scrapers y providers |
| Tests | `pytest` + `pytest-asyncio` + `respx` | Mocks de HTTP sin hits reales |
| Linting | `ruff` | Linter + formatter en uno |
| Type checking | `mypy --strict` | Sin `Any` sin justificación |
| Pre-commit | `pre-commit` | ruff + mypy antes de cada commit |
| Containers | `docker compose` | Ollama local opcional |
| CI | GitHub Actions | lint + tests en cada push/PR |

**Prohibido usar:** `requests`, `BeautifulSoup`, `scrapy`, `selenium`, `time.sleep()` en async.

---

## Estructura del proyecto

```
linkedin-intelligence/
├── CLAUDE.md
├── README.md
├── CHANGELOG.md
├── LICENSE                              ← MIT
├── .env.example
├── .gitignore
├── .pre-commit-config.yaml
├── pyproject.toml
├── docker-compose.yml
├── Makefile
│
├── .github/
│   └── workflows/
│       └── ci.yml                       ← lint + unit tests en push/PR
│
├── docs/
│   ├── ARCHITECTURE.md
│   └── DATA_SOURCES.md
│
├── data/
│   ├── .gitkeep
│   ├── raw/                             ← en .gitignore, nunca commiteado
│   │   ├── gdpr_export/
│   │   ├── jobs_scraped/
│   │   └── .session                    ← cookies Playwright, en .gitignore
│   ├── processed/                       ← en .gitignore, nunca commiteado
│   └── sample/                          ← SÍ commiteado, datos sintéticos
│       ├── gdpr/
│       │   ├── messages.csv
│       │   ├── connections.csv
│       │   ├── job_applications.csv
│       │   ├── Profile.csv
│       │   ├── Positions.csv
│       │   └── Skills.csv
│       └── jobs_sample.jsonl            ← jobs sintéticos pre-procesados
│                                           para demo de extract-skills sin API key
│
├── linkedin_intelligence/
│   ├── __init__.py                      ← __version__ = "0.1.0"
│   ├── config.py                        ← Settings singleton (pydantic-settings)
│   ├── cli.py                           ← Entry point typer
│   │
│   ├── providers/
│   │   ├── __init__.py                  ← factory get_provider()
│   │   ├── base.py                      ← Protocol LLMProvider + modelos Pydantic + prompts
│   │   ├── deepseek.py
│   │   ├── ollama.py
│   │   └── anthropic.py
│   │
│   ├── scrapers/
│   │   ├── __init__.py
│   │   ├── base.py                      ← AsyncScraper: login, sesión, retry, rate limit
│   │   └── jobs.py                      ← JobsScraper
│   │
│   ├── parsers/
│   │   ├── __init__.py
│   │   ├── gdpr.py                      ← GDPRParser: mensajes, conexiones, job apps
│   │   └── profile.py                   ← ProfileParser: UserProfile desde GDPR
│   │
│   ├── extractors/
│   │   ├── __init__.py
│   │   └── skills.py                    ← SkillsExtractor: batches + dedup + cache
│   │
│   └── analysis/
│       ├── __init__.py
│       ├── stats.py                     ← Agrega jobs + señales de mensajes de reclutadores
│       └── portfolio.py                 ← Genera sugerencias personalizadas con UserProfile
│
├── tests/
│   ├── conftest.py
│   ├── fixtures/
│   │   ├── jobs_list.html
│   │   └── job_detail.html
│   ├── unit/
│   │   ├── test_gdpr_parser.py
│   │   ├── test_profile_parser.py
│   │   ├── test_skills_extractor.py
│   │   ├── test_stats.py
│   │   └── test_providers.py
│   └── integration/
│       └── test_ollama_single_job.py    ← @pytest.mark.slow
│
└── output/
    └── .gitkeep
```

---

## Módulo `parsers/profile.py` — UserProfile

### Qué hace
Lee los CSVs de perfil del export GDPR y construye un `UserProfile` que:
- Se inyecta en el prompt de `portfolio.py` para personalizar sugerencias
- Auto-sugiere keywords de búsqueda si el usuario no las especifica en el CLI
- Se muestra como resumen al inicio del `run-all` para que el usuario confirme que el perfil detectado es correcto

### Modelo

```python
from pydantic import BaseModel

class WorkExperience(BaseModel):
    title: str
    company: str
    started_on: str       # ISO date
    finished_on: str | None  # None = posición actual

class UserProfile(BaseModel):
    full_name: str
    headline: str                    # título profesional del perfil
    current_role: str                # cargo más reciente en Positions.csv
    current_company: str | None
    domain: str                      # inferido por LLM: "AI/ML" | "Data" | "Backend" | etc.
    experience_years: int            # calculado desde Positions.csv
    declared_skills: list[str]       # de Skills.csv
    experience: list[WorkExperience]
    suggested_keywords: list[str]    # generados automáticamente
```

### Fuentes en el export GDPR

| Campo | Archivo GDPR | Columna |
|---|---|---|
| `full_name` | `Profile.csv` | `First Name` + `Last Name` |
| `headline` | `Profile.csv` | `Headline` |
| `current_role` | `Positions.csv` | fila sin `Finished On` |
| `declared_skills` | `Skills.csv` | `Name` |
| `experience` | `Positions.csv` | todos los registros |

### Inferencia de dominio y keywords
El parser llama al LLM **una sola vez** con el headline + cargo actual + skills declaradas
para inferir `domain` y generar `suggested_keywords`. Es una llamada barata (~200 tokens).

```python
PROFILE_PROMPT = """
Dado este perfil profesional, responde SOLO con JSON:
{
  "domain": "string (ej: AI/ML, Data Engineering, Backend, BI, DevOps...)",
  "suggested_keywords": ["lista de 5-8 búsquedas de LinkedIn relevantes para este perfil"]
}

Headline: {headline}
Cargo actual: {current_role}
Skills declaradas: {skills}
"""
```

### Integración con el resto del pipeline

```
parse-profile → UserProfile
    │
    ├──► CLI muestra resumen y pide confirmación antes de continuar
    ├──► scrape-jobs: usa suggested_keywords si no se pasan --keywords manualmente
    └──► analyze: UserProfile se inyecta en el prompt de portfolio.py
```

---

## Módulo `analysis/stats.py` — señales de mensajes

### El problema actual (gap resuelto)
Los mensajes de reclutadores se parseaban pero nunca se usaban en el análisis.
Son señal de mercado valiosa: qué roles buscan, qué skills mencionan, desde qué industrias.

### Qué añade ahora
`stats.py` lee tanto `jobs_enriched.jsonl` como `messages.jsonl` y combina dos fuentes:

```python
@dataclass
class MarketStats:
    # De jobs scrapeados
    top_tecnologias: list[SkillCount]
    top_skills_tecnicas: list[SkillCount]
    top_industrias: list[IndustryCount]
    seniority_distribution: dict[str, float]
    remote_pct: float

    # De mensajes de reclutadores (nuevo)
    recruiter_mentioned_roles: list[SkillCount]    # roles que reclutadores mencionan
    recruiter_mentioned_skills: list[SkillCount]   # skills que reclutadores mencionan
    inbound_recruiter_count: int                   # nº de mensajes inbound
    top_recruiter_industries: list[IndustryCount]  # de dónde vienen los recruiters
```

### Detección de mensajes de reclutador
`gdpr.py` añade el campo `is_recruiter: bool` a cada mensaje.
Heurística: sender no eres tú + keywords como "oportunidad", "encajarías", "posición", "role", "opportunity" en el subject o content.
No es perfecta pero cubre el 90% de los casos.

La extracción de skills de los mensajes de reclutadores usa el mismo provider LLM
con un prompt más ligero (solo roles y skills, no el schema completo).

---

## Módulo `extractors/skills.py` — runs incrementales

### El problema (gap resuelto)
Sin deduplicación, cada `extract-skills` reprocesa todos los jobs desde cero,
desperdiciando tokens de API y tiempo.

### Solución: caché por job ID

```python
class SkillsExtractor:
    def __init__(self, provider: LLMProvider, processed_path: Path) -> None:
        self._provider = provider
        self._cache_path = processed_path / "jobs_enriched.jsonl"
        self._processed_ids: set[str] = self._load_processed_ids()

    def _load_processed_ids(self) -> set[str]:
        """Lee el JSONL existente y devuelve el set de IDs ya procesados."""
        if not self._cache_path.exists():
            return set()
        ids = set()
        with self._cache_path.open() as f:
            for line in f:
                record = json.loads(line)
                ids.add(record["id"])
        return ids

    async def extract_batch(self, jobs: list[Job]) -> None:
        pending = [j for j in jobs if j.id not in self._processed_ids]
        logger.info(f"{len(pending)} jobs pendientes, {len(jobs) - len(pending)} ya procesados")
        # procesa solo pending, append-only al JSONL
```

El scraper también deduplica: antes de scrape-jobs, carga los IDs ya en
`jobs_scraped/*.jsonl` y no vuelve a visitar la misma URL.

---

## Módulo `providers/base.py` — diseño del contrato

```python
from typing import Protocol, runtime_checkable
from pydantic import BaseModel, model_validator

class ExtractedSkills(BaseModel):
    skills_tecnicas: list[str]
    skills_blandas: list[str]
    tecnologias: list[str]
    industria: str
    seniority: str        # "junior" | "mid" | "senior" | "unknown"
    remote: bool

    @model_validator(mode="before")
    @classmethod
    def normalize(cls, v: dict) -> dict:
        """Sanea listas None, strings en lugar de listas, etc."""
        ...

# Prompt compartido — todos los providers usan exactamente este
EXTRACTION_PROMPT: str = """..."""

PORTFOLIO_PROMPT: str = """
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

@runtime_checkable
class LLMProvider(Protocol):
    async def extract_skills(self, job_description: str) -> ExtractedSkills: ...
    async def extract_recruiter_signals(self, message: str) -> dict[str, list[str]]: ...
    async def suggest_portfolio(self, stats: MarketStats, profile: UserProfile) -> str: ...
    async def infer_profile_domain(self, headline: str, role: str, skills: list[str]) -> dict[str, str | list[str]]: ...
    async def health_check(self) -> bool: ...
```

---

## Progress bars con `rich`

Para operaciones largas, usar `rich.progress.Progress` en lugar de logs planos.
Especialmente crítico para `extract-skills` con Ollama donde cada job puede tardar 30s+.

```python
from rich.progress import Progress, SpinnerColumn, TimeElapsedColumn

async def extract_batch(self, jobs: list[Job]) -> None:
    with Progress(SpinnerColumn(), *Progress.get_default_columns(), TimeElapsedColumn()) as progress:
        task = progress.add_task("Extrayendo skills...", total=len(pending))
        for job in pending:
            await self._extract_one(job)
            progress.advance(task)
```

`rich` también se usa en el CLI para el resumen del `UserProfile` detectado
(tabla formateada antes de continuar el pipeline).

---

## Variables de entorno

```bash
# .env.example

# LLM Provider: "deepseek" | "ollama" | "anthropic"
LLM_PROVIDER=deepseek

DEEPSEEK_API_KEY=
DEEPSEEK_MODEL=deepseek-chat

ANTHROPIC_API_KEY=
ANTHROPIC_MODEL=claude-opus-4-5

OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:7b

LINKEDIN_EMAIL=
LINKEDIN_PASSWORD=

GDPR_EXPORT_PATH=data/raw/gdpr_export/
JOBS_OUTPUT_PATH=data/raw/jobs_scraped/
PROCESSED_PATH=data/processed/

MAX_JOBS_PER_KEYWORD=50
SCRAPE_DELAY_SECONDS=2.5

LOG_LEVEL=INFO
LOG_FILE=                          # opcional: ruta a archivo de log (para runs overnight)
```

Si `LOG_FILE` está definido, el logger escribe simultáneamente a consola y archivo.
Útil para runs de Ollama overnight donde no se monitorea la terminal.

---

## CLI — flujo completo y comandos

### Orden del pipeline en `run-all`
```
parse-profile → parse-gdpr → scrape-jobs → extract-skills → analyze
```

`parse-profile` corre primero y siempre. Si el GDPR export no está disponible,
el pipeline puede continuar sin perfil pero sin personalización ni keywords automáticas.

### Comandos

```bash
# Pipeline completo (con detección de perfil automática)
linkedin-intel run-all --location "Spain"
linkedin-intel run-all --keywords "ML engineer" "data scientist" --location "Spain"

# Pasos individuales
linkedin-intel parse-profile                          # detecta UserProfile del GDPR
linkedin-intel parse-gdpr                             # mensajes, conexiones, job apps
linkedin-intel scrape-jobs --location "Spain"         # usa keywords del perfil si no se pasan
linkedin-intel scrape-jobs --keywords "..." --since 2025-01-01  # solo jobs desde esa fecha
linkedin-intel extract-skills                         # solo procesa jobs no procesados aún
linkedin-intel analyze

# Utilidades
linkedin-intel scrape-jobs --dry-run                  # simula sin requests reales
linkedin-intel test-provider                          # health check del provider activo
linkedin-intel sample-run                             # pipeline con data/sample/ (sin credentials)
```

### Flag `--since`
`scrape-jobs --since YYYY-MM-DD` filtra solo ofertas publicadas después de esa fecha.
Útil para runs periódicos donde solo quieres analizar novedades.

---

## GitHub Actions CI

`.github/workflows/ci.yml` corre en cada push y PR:

```yaml
# jobs:
#   lint: ruff check + ruff format --check + mypy --strict
#   test: pytest tests/unit/ --cov=linkedin_intelligence --cov-fail-under=80
```

Los tests de integración (`@pytest.mark.slow`) NO corren en CI — requieren Ollama local.
El badge de CI va en el README.

---

## Testing

### Filosofía
- Unit tests: cero hits reales a LinkedIn ni LLM APIs
- `data/sample/jobs_sample.jsonl` permite testear `extract-skills` sin API key en `sample-run`
- `respx` intercepta todas las llamadas `httpx` en tests de providers
- `data/sample/gdpr/` cubre todos los parsers

### Test de integración Ollama
`tests/integration/test_ollama_single_job.py` — 1 job real, verifica el flujo completo.
`@pytest.mark.slow` — no corre en CI.

```bash
make ollama-up && make test-ollama
```

### Coverage objetivo
- `providers/`: 90%+
- `parsers/`: 95%+
- `analysis/`: 85%+
- `scrapers/`: 70%+

---

## Makefile

```
install        pip install -e ".[dev]"
lint           ruff check + ruff format --check + mypy --strict
format         ruff format
test           pytest tests/unit/ -v
test-all       pytest tests/ -v
test-ollama    pytest tests/integration/ -v -m slow
test-cov       pytest tests/unit/ --cov=linkedin_intelligence --cov-report=term-missing
ollama-up      docker compose up -d + model pull
ollama-down    docker compose down
sample-run     linkedin-intel sample-run
ci             lint + test (replica el check de GitHub Actions localmente)
setup-github   configura el repo en GitHub via gh CLI (branch protection, topics, descripción)
clean          borra __pycache__, .pytest_cache, .mypy_cache, dist/
```

---

## GitHub setup — configuración post-creación del repo

Una vez que el repo existe en GitHub, correr:

```bash
make setup-github
```

Esto ejecuta `scripts/setup_github.sh` via `gh` CLI y configura automáticamente:

- **Descripción y topics** del repo (`python`, `linkedin`, `llm`, `playwright`, `deepseek`, `ollama`, etc.)
- **Branch protection en `main`**:
  - PR obligatorio antes de merge (1 aprobación requerida)
  - Review de CODEOWNERS requerida (todos los PRs van a `@nico150891`)
  - CI checks deben pasar (`lint` + `test`)
  - Reviews descartadas cuando hay nuevos commits
  - Force push bloqueado
  - Borrado de rama bloqueado
  - `enforce_admins=false` → el admin (tú) puede pushear directo a main si quiere
- **Wiki y Projects desactivados** (no se usan)
- **Delete branch on merge** activado (limpieza automática de ramas)

### Prerrequisito
```bash
gh auth status   # debe mostrar tu cuenta autenticada
```

### Orden de operaciones al crear el repo
```bash
# 1. Crear el repo (si no existe todavía)
gh repo create nico150891/linkedin-intelligence --public --source=. --remote=origin

# 2. Primer push (main debe existir para aplicar branch protection)
git add . && git commit -m "chore: initial project skeleton"
git push -u origin main

# 3. Configurar GitHub
make setup-github
```

⚠️ `make setup-github` falla si `main` no existe todavía en el remoto — siempre hacer el primer push antes.

---

## .gitignore — reglas críticas

```gitignore
.env
data/raw/
data/processed/
data/**/.session
data/**/*.cookies
output/*.json
output/*.md
__pycache__/
*.pyc
.pytest_cache/
.mypy_cache/
.ruff_cache/
dist/
*.egg-info/
*.log
```

**Sí commiteado:** `data/sample/`, `data/.gitkeep`, `output/.gitkeep`

---

## Lo que NO hacer

- ❌ `time.sleep()` en código async
- ❌ `dict[str, Any]` entre módulos — definir el modelo Pydantic
- ❌ Selectores CSS hardcodeados en múltiples sitios
- ❌ Llamar al LLM con texto vacío o < 100 chars — validar antes
- ❌ Silenciar excepciones con `pass`
- ❌ Commitear `.env`, `data/raw/`, `data/processed/`
- ❌ `print()` en producción — usar `logging` o `rich`
- ❌ Re-extraer jobs ya procesados — respetar la caché por ID
- ❌ Tests con hits reales sin `@pytest.mark.slow`
- ❌ Mezclar lógica de provider con lógica de negocio
