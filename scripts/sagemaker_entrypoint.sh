#!/usr/bin/env bash
# scripts/sagemaker_entrypoint.sh
#
# Entrypoint for the SageMaker Processing Job.
# Installs Ollama, pulls the model, runs the linkedin-intel pipeline,
# and writes results to /opt/ml/processing/output/.
#
# Expected SageMaker inputs:
#   /opt/ml/processing/input/code/   <- project source code
#   /opt/ml/processing/input/gdpr/   <- GDPR export CSVs
#   /opt/ml/processing/input/jobs/   <- scraped jobs (optional)
#
# Output:
#   /opt/ml/processing/output/       <- enriched jobs, stats, portfolio suggestions

set -euo pipefail

# ── Paths ────────────────────────────────────────────────────────────────────
CODE_DIR=/opt/ml/processing/input/code
GDPR_DIR=/opt/ml/processing/input/gdpr
JOBS_DIR=/opt/ml/processing/input/jobs
OUTPUT_DIR=/opt/ml/processing/output

PROCESSED_DIR="$OUTPUT_DIR/processed"
mkdir -p "$PROCESSED_DIR"

echo "══════════════════════════════════════════════════════════════"
echo "  linkedin-intelligence — SageMaker Processing Job"
echo "══════════════════════════════════════════════════════════════"

# ── 1. GPU check ─────────────────────────────────────────────────────────────
echo ""
echo ">>> Checking GPU..."
if nvidia-smi > /dev/null 2>&1; then
    nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
else
    echo "WARNING: No GPU detected — Ollama will run on CPU (slower)"
fi

# ── 2. Install Ollama ────────────────────────────────────────────────────────
echo ""
echo ">>> Installing Ollama..."
curl -fsSL https://ollama.com/install.sh | sh

# ── 3. Start Ollama server ───────────────────────────────────────────────────
echo ""
echo ">>> Starting Ollama server..."
ollama serve &
OLLAMA_PID=$!

echo "Waiting for Ollama to be ready..."
for i in $(seq 1 60); do
    if curl -sf http://localhost:11434/api/tags > /dev/null 2>&1; then
        echo "Ollama ready (attempt $i)"
        break
    fi
    if [ "$i" -eq 60 ]; then
        echo "ERROR: Ollama did not start after 120s"
        exit 1
    fi
    sleep 2
done

# ── 4. Pull model ───────────────────────────────────────────────────────────
MODEL="${OLLAMA_MODEL:-qwen2.5:7b}"
echo ""
echo ">>> Pulling model: $MODEL"
ollama pull "$MODEL"
echo "Model ready."

# ── 5. Install project ──────────────────────────────────────────────────────
echo ""
echo ">>> Installing linkedin-intelligence..."
cd "$CODE_DIR"

# DLC image has Python 3.11; relax the >=3.12 constraint for runtime
sed -i 's/requires-python = ">=3.12"/requires-python = ">=3.10"/' pyproject.toml

pip install --quiet --no-cache-dir .
echo "Installed: $(linkedin-intel --help | head -1)"

# ── 6. Configure environment ────────────────────────────────────────────────
export LLM_PROVIDER=ollama
export OLLAMA_BASE_URL=http://localhost:11434
export OLLAMA_MODEL="$MODEL"
export GDPR_EXPORT_PATH="$GDPR_DIR"
export PROCESSED_PATH="$PROCESSED_DIR"
export LOG_LEVEL=INFO

# ── 7. Run pipeline ─────────────────────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════════════════════════"
echo "  Pipeline start"
echo "══════════════════════════════════════════════════════════════"

# Step 1: Parse profile (calls LLM once for domain inference)
echo ""
echo ">>> Step 1/4: parse-profile"
linkedin-intel parse-profile

# Step 2: Parse GDPR (no LLM)
echo ""
echo ">>> Step 2/4: parse-gdpr"
linkedin-intel parse-gdpr

# Step 3: Extract skills (heavy LLM work)
HAS_JOBS=false
if [ -d "$JOBS_DIR" ] && ls "$JOBS_DIR"/*.jsonl 1>/dev/null 2>&1; then
    HAS_JOBS=true
    export JOBS_OUTPUT_PATH="$JOBS_DIR"
fi

if [ "$HAS_JOBS" = true ]; then
    echo ""
    echo ">>> Step 3/4: extract-skills ($(ls "$JOBS_DIR"/*.jsonl | wc -l) files found)"
    linkedin-intel extract-skills

    echo ""
    echo ">>> Step 4/4: analyze"
    linkedin-intel analyze
else
    echo ""
    echo ">>> No scraped jobs found in $JOBS_DIR — skipping extract-skills and analyze"
    echo "    To include jobs, upload them via --jobs-path in the launcher."
fi

# ── 8. Copy any generated output ────────────────────────────────────────────
if [ -f "output/portfolio_suggestions.md" ]; then
    cp output/portfolio_suggestions.md "$OUTPUT_DIR/"
fi

# ── 9. Cleanup ───────────────────────────────────────────────────────────────
kill "$OLLAMA_PID" 2>/dev/null || true

echo ""
echo "══════════════════════════════════════════════════════════════"
echo "  Pipeline complete. Results in $OUTPUT_DIR"
echo "══════════════════════════════════════════════════════════════"
ls -lh "$OUTPUT_DIR"/
ls -lh "$PROCESSED_DIR"/ 2>/dev/null || true
