"""Application settings and logging configuration."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM provider
    llm_provider: Literal["deepseek", "ollama", "anthropic"] = "deepseek"

    # DeepSeek
    deepseek_api_key: SecretStr = SecretStr("")
    deepseek_model: str = "deepseek-chat"

    # Anthropic
    anthropic_api_key: SecretStr = SecretStr("")
    anthropic_model: str = "claude-opus-4-5"

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"

    # LinkedIn credentials
    linkedin_email: str = ""
    linkedin_password: SecretStr = SecretStr("")

    # Paths
    gdpr_export_path: Path = Path("data/raw/gdpr_export/")
    jobs_output_path: Path = Path("data/raw/jobs_scraped/")
    processed_path: Path = Path("data/processed/")

    # Scraping
    max_jobs_per_keyword: int = 50
    scrape_delay_seconds: float = 2.5

    # Logging
    log_level: str = "INFO"
    log_file: str = ""

    @model_validator(mode="after")
    def validate_provider_keys(self) -> Settings:
        """Ensure the active provider has its API key configured."""
        if self.llm_provider == "deepseek" and not self.deepseek_api_key.get_secret_value():
            msg = (
                "LLM_PROVIDER is 'deepseek' but DEEPSEEK_API_KEY is empty. "
                "Set it in .env or switch to another provider."
            )
            raise ValueError(msg)
        if self.llm_provider == "anthropic" and not self.anthropic_api_key.get_secret_value():
            msg = (
                "LLM_PROVIDER is 'anthropic' but ANTHROPIC_API_KEY is empty. "
                "Set it in .env or switch to another provider."
            )
            raise ValueError(msg)
        return self


def _setup_logging(s: Settings) -> None:
    """Configure root logger based on settings."""
    root = logging.getLogger()
    root.setLevel(s.log_level.upper())

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(formatter)
    root.addHandler(console)

    if s.log_file:
        file_handler = logging.FileHandler(s.log_file)
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)


def get_settings() -> Settings:
    """Create and return a Settings instance. Validates on construction."""
    return Settings()


# Deferred initialization — import config but call get_settings() explicitly
# so tests can set env vars before validation runs.
