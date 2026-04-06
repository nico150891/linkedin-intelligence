.PHONY: install lint format test test-all test-ollama test-cov ollama-up ollama-down sample-run ci setup-github clean

install:
	pip install -e ".[dev,test]"

lint:
	ruff check linkedin_intelligence/ tests/
	ruff format --check linkedin_intelligence/ tests/
	mypy --strict linkedin_intelligence/

format:
	ruff format linkedin_intelligence/ tests/

test:
	pytest tests/unit/ -v

test-all:
	pytest tests/ -v

test-ollama:
	pytest tests/integration/ -v -m slow

test-cov:
	pytest tests/unit/ --cov=linkedin_intelligence --cov-report=term-missing

ollama-up:
	docker compose up -d
	@echo "Waiting for Ollama to be ready..."
	@until curl -sf http://localhost:11434/api/tags > /dev/null 2>&1; do sleep 1; done
	docker compose exec ollama ollama pull qwen2.5:7b

ollama-down:
	docker compose down

sample-run:
	linkedin-intel sample-run

ci: lint test

setup-github:
	bash scripts/setup_github.sh

clean:
	rm -rf __pycache__ .pytest_cache .mypy_cache .ruff_cache dist *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
