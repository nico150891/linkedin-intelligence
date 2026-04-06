# ARCHITECTURE.md — Flujo de datos

## Diagrama general

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           FUENTES DE DATOS                              │
├──────────────────────┬───────────────────────┬──────────────────────────┤
│    Export GDPR       │   LinkedIn Jobs        │    data/sample/          │
│    (manual)          │   (Playwright)         │    (demo / tests)        │
│                      │                        │                          │
│  Profile.csv    ─────┼──► parse-profile       │  gdpr/*.csv              │
│  Positions.csv  ─────┘                        │  jobs_sample.jsonl       │
│  Skills.csv     ─────┐                        │                          │
│  messages.csv        │                        │                          │
│  connections.csv     │                        │                          │
│  job_applications    │                        │                          │
└──────────────────────┼────────────────────────┴──────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      parsers/profile.py                                 │
│                                                                         │
│  Lee Profile.csv + Positions.csv + Skills.csv                           │
│  Llama al LLM UNA vez (~200 tokens) para inferir domain + keywords      │
│                                                                         │
│  Output: UserProfile {                                                  │
│    full_name, headline, current_role, current_company,                  │
│    domain, experience_years, declared_skills,                           │
│    suggested_keywords                                                   │
│  }                                                                      │
└─────────────────┬────────────────────────────────────────────────────────┘
                  │
        ┌─────────┴──────────────────────────┐
        │                                    │
        ▼                                    ▼
┌───────────────────────┐    ┌──────────────────────────────────────────────┐
│  CLI muestra resumen  │    │  scrapers/jobs.py                            │
│  del perfil detectado │    │                                              │
│  y pide confirmación  │    │  Si no hay --keywords en CLI:                │
│  antes de continuar   │    │    usa profile.suggested_keywords            │
└───────────────────────┘    │  Si hay --since: filtra por fecha            │
                             │                                              │
                             │  Deduplicación: carga IDs de jobs ya        │
                             │  scrapeados y salta URLs repetidas           │
                             │                                              │
                             │  Output: data/raw/jobs_scraped/              │
                             │          jobs_YYYYMMDD.jsonl (append)        │
                             └─────────────────┬────────────────────────────┘
                                               │
┌──────────────────────────────────────────────┴──────────────────────────┐
│                             data/raw/                                   │
│                                                                         │
│  gdpr_export/                    jobs_scraped/                          │
│  ├── messages.csv                └── jobs_YYYYMMDD.jsonl                │
│  ├── connections.csv                 {id, title, company, location,     │
│  ├── job_applications.csv             description, url, scraped_at}     │
│  ├── Profile.csv                                                        │
│  ├── Positions.csv                                                      │
│  └── Skills.csv                                                         │
└──────────┬──────────────────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                      parsers/gdpr.py                                     │
│                                                                          │
│  • Normaliza fechas a ISO 8601                                           │
│  • Limpia BOM, encoding UTF-8                                            │
│  • Deduplica mensajes por thread/ID                                      │
│  • Detecta mensajes de reclutadores (is_recruiter: bool)                 │
│    Heurística: sender ≠ yo + keywords {"oportunidad", "role", "fit"...}  │
└──────────┬───────────────────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                         data/processed/                                  │
│                                                                          │
│  messages.jsonl           connections.jsonl      jobs_clean.jsonl        │
│  ──────────────────        ─────────────────      ──────────────────     │
│  {sender, text,            {name, company,        {id, title,            │
│   date, thread_id,          position,              company, location,    │
│   is_recruiter}             connected_at}          description, url}     │
└──────────┬───────────────────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                      extractors/skills.py                                │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  Caché incremental                                              │    │
│  │  • Carga IDs ya en jobs_enriched.jsonl                          │    │
│  │  • Solo procesa jobs con ID no visto                            │    │
│  │  • Loggea: "47 pendientes, 303 ya procesados"                   │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  Procesamiento en batch                                         │    │
│  │  • asyncio.gather() con Semaphore(10)                           │    │
│  │  • rich.Progress con tiempo transcurrido                        │    │
│  │  • Job fallido → logger.warning + continúa                      │    │
│  │  • Append-only al JSONL (seguro ante interrupciones)            │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  Procesa también mensajes de reclutadores (is_recruiter=True)            │
│  con un prompt más ligero → recruiter_signals.jsonl                      │
└──────────┬────────────────────────┬─────────────────────────────────────┘
           │                        │
           │            ┌───────────▼──────────────────────────────────────┐
           │            │      providers/  (LLMProvider Protocol)           │
           │            │                                                   │
           │            │  ┌────────────┐  ┌─────────┐  ┌──────────────┐  │
           │            │  │  DeepSeek  │  │  Ollama │  │  Anthropic   │  │
           │            │  │  (default) │  │  local  │  │              │  │
           │            │  │            │  │         │  │              │  │
           │            │  │  httpx     │  │  httpx  │  │  SDK async   │  │
           │            │  │  api.deep  │  │  :11434 │  │              │  │
           │            │  │  seek.com  │  │         │  │              │  │
           │            │  └────────────┘  └─────────┘  └──────────────┘  │
           │            │                                                   │
           │            │  Todos implementan:                               │
           │            │  • extract_skills(description) → ExtractedSkills  │
           │            │  • extract_recruiter_signals(msg) → dict          │
           │            │  • suggest_portfolio(stats, profile) → str        │
           │            │  • infer_profile_domain(...) → dict               │
           │            │  • health_check() → bool                          │
           │            └───────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                       data/processed/                                    │
│                                                                          │
│  jobs_enriched.jsonl                    recruiter_signals.jsonl          │
│  ───────────────────────────────        ───────────────────────────      │
│  {id, title, company, location,         {thread_id, sender_company,     │
│   remote, url, description,              mentioned_roles,                │
│   scraped_at,                            mentioned_skills,               │
│   skills_tecnicas, skills_blandas,       date}                           │
│   tecnologias, industria, seniority,                                     │
│   extracted_at, extraction_provider}                                     │
└──────────┬───────────────────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                        analysis/stats.py                                 │
│                                                                          │
│  Fuente 1 — jobs_enriched.jsonl                                          │
│  • Counter(tecnologias)         → top 20 con frecuencia y %              │
│  • Counter(skills_tecnicas)     → top 20                                 │
│  • Counter(industria)           → top 10                                 │
│  • Counter(seniority)           → distribución                           │
│  • % remote                                                              │
│  • Co-ocurrencia de skills                                               │
│                                                                          │
│  Fuente 2 — recruiter_signals.jsonl (NUEVO)                              │
│  • Counter(mentioned_roles)     → roles que reclutadores buscan          │
│  • Counter(mentioned_skills)    → skills que reclutadores mencionan      │
│  • inbound_recruiter_count                                               │
│  • top_recruiter_industries                                              │
│                                                                          │
│  Output: MarketStats dataclass → output/stats.json                       │
└──────────┬───────────────────────────────────────────────────────────────┘
           │
           ├─────────────────────────┐
           ▼                         ▼
┌──────────────────────┐   ┌──────────────────────────────────────────────┐
│  output/stats.json   │   │  analysis/portfolio.py                       │
│                      │   │                                              │
│  {                   │   │  Inputs:                                     │
│   top_tecnologias,   │   │  • MarketStats (de stats.json)               │
│   top_skills,        │   │  • UserProfile (de parse-profile)            │
│   top_industrias,    │   │                                              │
│   seniority_dist,    │   │  Prompt personalizado con:                   │
│   remote_pct,        │   │  • El rol/dominio/experience del usuario     │
│   recruiter_signals  │   │  • Top tecnologías del mercado               │
│  }                   │   │  • Gap entre skills declaradas y demandadas  │
└──────────────────────┘   │                                              │
                           │  → provider.suggest_portfolio(stats, profile) │
                           └──────────────────┬───────────────────────────┘
                                              │
                                              ▼
                           ┌──────────────────────────────────────────────┐
                           │       output/portfolio_suggestions.md        │
                           │                                              │
                           │  # Portfolio Suggestions for Nicolás Leiva  │
                           │  *Head of AI / AI Engineer — 8 yrs exp*     │
                           │  *Based on 350 job listings analyzed*        │
                           │                                              │
                           │  ## 1. Production LLM Gateway with FastAPI   │
                           │  **Stack:** Python, FastAPI, LiteLLM, Redis  │
                           │  **Demand:** appears in 71% of listings      │
                           │  **Why for you:** bridges your LLM exp with  │
                           │  the MLOps gap most listings require         │
                           │  **Difficulty:** Medium — 2-3 weekends       │
                           └──────────────────────────────────────────────┘
```

---

## Flujo de runs incrementales

```
Primera ejecución:
  scrape-jobs    → scrapes 350 jobs  → jobs_scraped/jobs_20250120.jsonl (350 registros)
  extract-skills → extrae 350 jobs   → jobs_enriched.jsonl (350 registros)

Segunda ejecución (1 semana después):
  scrape-jobs    → scrapes 50 nuevos → jobs_scraped/jobs_20250127.jsonl (50 registros)
                   (los 300 repetidos se saltean por URL/ID)
  extract-skills → extrae 50 nuevos  → jobs_enriched.jsonl (ahora 400 registros)
                   (los 350 ya procesados se saltean por ID)
```

**Clave:** `jobs_enriched.jsonl` crece de forma append-only. Nunca se sobreescribe.
El análisis siempre lee el archivo completo para estadísticas acumuladas.

---

## Decisiones de diseño

### ¿Por qué `Protocol` en vez de clase base abstracta (ABC)?
Permite duck typing estructural — cualquier objeto con los métodos correctos es un
`LLMProvider` válido sin herencia forzada. Facilita mocking en tests y añadir providers
sin modificar código existente.

### ¿Por qué JSONL y no SQLite?
- Append-only: interrupciones no corrompen datos ya procesados
- Streaming: procesable línea a línea sin cargar todo en memoria
- Inspeccionable con `head`, `tail`, `jq` directamente desde terminal
- Si el proyecto crece a queries complejas multi-tabla, SQLite es el siguiente paso lógico

### ¿Por qué `rich` en lugar de `tqdm`?
`rich` ya cubre logging formateado, tablas para el resumen de UserProfile, y barras
de progreso — una sola dependencia en lugar de dos. `tqdm` solo hace progress bars.

### ¿Por qué `qwen2.5:7b` para Ollama con 32GB RAM?
- 7B cabe holgado en RAM, dejando margen para el sistema
- Qwen 2.5 tiene excelente rendimiento en instrucciones estructuradas (JSON)
- Modelos más grandes (13B+) en CPU puro son demasiado lentos para ser útiles

### ¿Por qué `--since` en el scraper y no un cron?
El proyecto es personal y de baja frecuencia de uso. `--since` da el control
al usuario sin añadir complejidad de scheduling. Un cron o GitHub Action scheduled
es una extensión natural si se quiere automatizar.

### ¿Por qué los mensajes de reclutadores no van a una tabla separada de stats?
Se integran en `MarketStats` como campos de primer nivel porque el consumidor
(el prompt de `portfolio.py`) los necesita en la misma estructura. Separarlos
requeriría más joins conceptuales sin beneficio real dado el scope del proyecto.
