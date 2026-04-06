"""LLM provider factory."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from linkedin_intelligence.config import Settings
    from linkedin_intelligence.providers.base import LLMProvider


def get_provider(settings: Settings) -> LLMProvider:
    """Instantiate the LLM provider configured in *settings*."""
    match settings.llm_provider:
        case "deepseek":
            from linkedin_intelligence.providers.deepseek import DeepSeekProvider

            return DeepSeekProvider(
                api_key=settings.deepseek_api_key.get_secret_value(),
                model=settings.deepseek_model,
            )
        case "ollama":
            from linkedin_intelligence.providers.ollama import OllamaProvider

            return OllamaProvider(
                base_url=settings.ollama_base_url,
                model=settings.ollama_model,
            )
        case "anthropic":
            from linkedin_intelligence.providers.anthropic import AnthropicProvider

            return AnthropicProvider(
                api_key=settings.anthropic_api_key.get_secret_value(),
                model=settings.anthropic_model,
            )
        case _:
            msg = f"Unknown LLM provider: {settings.llm_provider}"
            raise ValueError(msg)
