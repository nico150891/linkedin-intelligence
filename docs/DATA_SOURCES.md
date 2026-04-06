# DATA_SOURCES.md — Fuentes de datos

## Fuente 1: Export GDPR de LinkedIn

### Qué contiene
LinkedIn exporta todo lo que tiene sobre ti en CSVs. Los relevantes para este proyecto:

| Archivo | Contenido | Usado |
|---|---|---|
| `messages.csv` | Todos tus mensajes con sender, texto y fecha | ✅ |
| `connections.csv` | Conexiones con empresa, cargo y fecha | ✅ |
| `Job Applications.csv` | Empleos a los que aplicaste | ✅ |
| `Positions.csv` | Tu historial laboral | ⬜ futuro |
| `Skills.csv` | Skills declaradas en tu perfil | ⬜ futuro |

### Cómo descargarlo
1. LinkedIn → **Yo** → **Configuración y privacidad**
2. **Privacidad de datos** → **Obtener una copia de tus datos**
3. Seleccionar: "Quiero una copia de mis datos" → marcar todo
4. Esperar entre 10 min y 24h (recibirás email con el link)
5. El ZIP expira en 72h — descargarlo enseguida

### Dónde colocarlo
```bash
unzip linkedin-export-*.zip -d data/raw/gdpr_export/
```

### Quirks del formato
- UTF-8 con BOM en algunos archivos — el parser lo maneja con `utf-8-sig`
- Fechas en `YYYY-MM-DD HH:MM:SS UTC` — se normalizan a ISO 8601
- `messages.csv`: el campo `CONTENT` puede tener saltos de línea dentro del valor
- Algunos campos vienen vacíos — el parser no falla, los trata como `None`

### Columnas relevantes

**`messages.csv`**
```
CONVERSATION ID, FROM, TO, DATE, SUBJECT, CONTENT, FOLDER
```

**`connections.csv`**
```
First Name, Last Name, Email Address, Company, Position, Connected On
```

**`Job Applications.csv`**
```
Company Name, Job Title, Applied At, Status
```

---

## Fuente 2: Scraping de ofertas de trabajo

### Qué scrapeamos y cómo
URL base: `https://www.linkedin.com/jobs/search/`

Parámetros usados:
```
?keywords=<keyword>
&location=<location>
&f_TPR=r604800     # publicadas en la última semana
&start=0           # paginación, incrementar de 25 en 25
```

El scraper navega en **dos pasos** por cada job:

1. **Lista de resultados**: extrae título, empresa, ubicación, URL de cada card
2. **Página de detalle**: extrae la descripción completa (necesaria para el LLM)

> Con `SCRAPE_DELAY_SECONDS=2.5` y 50 jobs/keyword: ~2 min por keyword.
> 7 keywords → ~14 minutos totales de scraping.

### Keywords de ejemplo para AI/ML engineer

```python
DEFAULT_KEYWORDS = [
    "machine learning engineer",
    "AI engineer",
    "MLOps engineer",
    "LLM engineer",
    "data scientist",
    "Python backend engineer",
    "NLP engineer",
]
```

### Sesión y autenticación
- Primer run: abre browser en modo visual para hacer login manualmente
- Guarda cookies en `data/raw/.session` (en `.gitignore`)
- Runs posteriores: reutiliza sesión sin login
- Para resetear: `rm data/raw/.session`

### Selectores CSS
Centralizados como constantes en `scrapers/jobs.py`. LinkedIn cambia su HTML con frecuencia;
si el scraper falla, los selectores son lo primero a revisar.

---

## Fuente 3: data/sample/ — datos sintéticos

### Para qué sirve
Datos de muestra commiteados al repo que permiten:
- Correr el pipeline completo sin credenciales (`linkedin-intel sample-run`)
- Ejecutar tests de parsers sin datos reales
- Que cualquier persona clone el repo y pruebe en 5 minutos

### Estructura de los CSVs sintéticos

**`messages.csv`**
```csv
CONVERSATION ID,FROM,TO,DATE,SUBJECT,CONTENT,FOLDER
conv_001,Elena Martínez <elena@acme.com>,you,2024-11-15 09:32:00 UTC,Oportunidad ML Engineer,"Hola! Vi tu perfil...",INBOX
```

**`connections.csv`**
```csv
First Name,Last Name,Email Address,Company,Position,Connected On
Carlos,López,,Acme Corp,Data Engineer,15 Nov 2024
```

**`job_applications.csv`**
```csv
Company Name,Job Title,Applied At,Status
Startup XYZ,Senior Python Developer,2024-10-01,Pending
```

~25 registros por archivo — suficiente para tests representativos.

---

## Providers LLM — comparativa

| Provider | Setup | Coste (350 jobs) | Velocidad | Calidad JSON |
|---|---|---|---|---|
| DeepSeek | API key | ~$0.15 | ~2 min | ⭐⭐⭐⭐ |
| Ollama (qwen2.5:7b) | Docker local | $0 | ~60-90 min CPU | ⭐⭐⭐ |
| Anthropic | API key | ~$1.80 | ~4 min | ⭐⭐⭐⭐⭐ |

**Recomendación por caso de uso:**
- Uso habitual → DeepSeek (precio/rendimiento)
- Sin internet o privacidad total → Ollama overnight
- Máxima calidad o descripciones en varios idiomas → Anthropic
