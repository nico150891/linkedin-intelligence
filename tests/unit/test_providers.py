"""Tests for LLM provider modules."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import respx

from linkedin_intelligence.providers.base import (
    ExtractedSkills,
    IndustryCount,
    MarketStats,
    SkillCount,
    UserProfile,
    WorkExperience,
)
from linkedin_intelligence.providers.deepseek import DeepSeekProvider
from linkedin_intelligence.providers.ollama import OllamaProvider

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_EXTRACTED_JSON: dict[str, Any] = {
    "skills_tecnicas": ["Python", "ML"],
    "skills_blandas": ["teamwork"],
    "tecnologias": ["TensorFlow"],
    "industria": "AI",
    "seniority": "senior",
    "remote": True,
}

_RECRUITER_JSON: dict[str, Any] = {
    "roles": ["ML Engineer"],
    "skills": ["Python", "PyTorch"],
}

_PROFILE_JSON: dict[str, Any] = {
    "domain": "AI/ML",
    "suggested_keywords": ["machine learning engineer", "ML engineer"],
}


def _make_profile() -> UserProfile:
    return UserProfile(
        full_name="Test User",
        headline="ML Engineer",
        current_role="Senior ML Engineer",
        current_company="TestCorp",
        domain="AI/ML",
        experience_years=5,
        declared_skills=["Python", "TensorFlow"],
        experience=[
            WorkExperience(
                title="Senior ML Engineer",
                company="TestCorp",
                started_on="2020-01-01",
                finished_on=None,
            ),
        ],
        suggested_keywords=["ML engineer"],
    )


def _make_stats() -> MarketStats:
    return MarketStats(
        top_tecnologias=[SkillCount("Python", 50), SkillCount("TensorFlow", 30)],
        top_skills_tecnicas=[SkillCount("ML", 40)],
        top_industrias=[IndustryCount("AI", 20)],
        seniority_distribution={"senior": 0.6, "mid": 0.4},
        remote_pct=0.5,
    )


# ---------------------------------------------------------------------------
# ExtractedSkills model tests
# ---------------------------------------------------------------------------


class TestExtractedSkills:
    def test_valid_input(self) -> None:
        skills = ExtractedSkills.model_validate(_EXTRACTED_JSON)
        assert skills.skills_tecnicas == ["Python", "ML"]
        assert skills.industria == "AI"
        assert skills.seniority == "senior"
        assert skills.remote is True

    def test_normalize_none_lists(self) -> None:
        data = {**_EXTRACTED_JSON, "skills_tecnicas": None, "skills_blandas": None}
        skills = ExtractedSkills.model_validate(data)
        assert skills.skills_tecnicas == []
        assert skills.skills_blandas == []

    def test_normalize_string_to_list(self) -> None:
        data = {**_EXTRACTED_JSON, "tecnologias": "TensorFlow"}
        skills = ExtractedSkills.model_validate(data)
        assert skills.tecnologias == ["TensorFlow"]

    def test_normalize_none_seniority(self) -> None:
        data = {**_EXTRACTED_JSON, "seniority": None}
        skills = ExtractedSkills.model_validate(data)
        assert skills.seniority == "unknown"

    def test_normalize_none_industria(self) -> None:
        data = {**_EXTRACTED_JSON, "industria": None}
        skills = ExtractedSkills.model_validate(data)
        assert skills.industria == "unknown"

    def test_normalize_none_remote(self) -> None:
        data = {**_EXTRACTED_JSON, "remote": None}
        skills = ExtractedSkills.model_validate(data)
        assert skills.remote is False


# ---------------------------------------------------------------------------
# DeepSeek provider tests
# ---------------------------------------------------------------------------


def _deepseek_response(content: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={"choices": [{"message": {"content": content}}]},
    )


class TestDeepSeekProvider:
    @respx.mock
    async def test_extract_skills(self) -> None:
        respx.post("https://api.deepseek.com/chat/completions").mock(
            return_value=_deepseek_response(json.dumps(_EXTRACTED_JSON))
        )
        provider = DeepSeekProvider(api_key="test-key")
        result = await provider.extract_skills("Test job description about ML.")
        assert isinstance(result, ExtractedSkills)
        assert result.industria == "AI"

    @respx.mock
    async def test_extract_skills_with_fenced_json(self) -> None:
        fenced = f"```json\n{json.dumps(_EXTRACTED_JSON)}\n```"
        respx.post("https://api.deepseek.com/chat/completions").mock(
            return_value=_deepseek_response(fenced)
        )
        provider = DeepSeekProvider(api_key="test-key")
        result = await provider.extract_skills("Test job description.")
        assert result.skills_tecnicas == ["Python", "ML"]

    @respx.mock
    async def test_extract_recruiter_signals(self) -> None:
        respx.post("https://api.deepseek.com/chat/completions").mock(
            return_value=_deepseek_response(json.dumps(_RECRUITER_JSON))
        )
        provider = DeepSeekProvider(api_key="test-key")
        result = await provider.extract_recruiter_signals("Looking for an ML Engineer.")
        assert result["roles"] == ["ML Engineer"]
        assert "Python" in result["skills"]

    @respx.mock
    async def test_suggest_portfolio(self) -> None:
        respx.post("https://api.deepseek.com/chat/completions").mock(
            return_value=_deepseek_response("## Project 1\nBuild an ML pipeline")
        )
        provider = DeepSeekProvider(api_key="test-key")
        result = await provider.suggest_portfolio(_make_stats(), _make_profile())
        assert "Project" in result

    @respx.mock
    async def test_infer_profile_domain(self) -> None:
        respx.post("https://api.deepseek.com/chat/completions").mock(
            return_value=_deepseek_response(json.dumps(_PROFILE_JSON))
        )
        provider = DeepSeekProvider(api_key="test-key")
        result = await provider.infer_profile_domain(
            headline="ML Engineer",
            role="Senior ML Engineer",
            skills=["Python", "TensorFlow"],
        )
        assert result["domain"] == "AI/ML"
        assert isinstance(result["suggested_keywords"], list)

    @respx.mock
    async def test_health_check_success(self) -> None:
        respx.post("https://api.deepseek.com/chat/completions").mock(
            return_value=httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})
        )
        provider = DeepSeekProvider(api_key="test-key")
        assert await provider.health_check() is True

    @respx.mock
    async def test_health_check_failure(self) -> None:
        respx.post("https://api.deepseek.com/chat/completions").mock(
            return_value=httpx.Response(500)
        )
        provider = DeepSeekProvider(api_key="test-key")
        assert await provider.health_check() is False

    @respx.mock
    async def test_chat_empty_choices_raises(self) -> None:
        respx.post("https://api.deepseek.com/chat/completions").mock(
            return_value=httpx.Response(200, json={"choices": []})
        )
        provider = DeepSeekProvider(api_key="test-key")
        with pytest.raises(ValueError, match="Unexpected DeepSeek response"):
            await provider.extract_skills("test")

    @respx.mock
    async def test_recruiter_signals_non_list_fallback(self) -> None:
        bad_json = {"roles": "not a list", "skills": 123}
        respx.post("https://api.deepseek.com/chat/completions").mock(
            return_value=_deepseek_response(json.dumps(bad_json))
        )
        provider = DeepSeekProvider(api_key="test-key")
        result = await provider.extract_recruiter_signals("test message")
        assert result["roles"] == []
        assert result["skills"] == []

    @respx.mock
    async def test_infer_domain_non_string_fallback(self) -> None:
        bad_json = {"domain": 123, "suggested_keywords": "not a list"}
        respx.post("https://api.deepseek.com/chat/completions").mock(
            return_value=_deepseek_response(json.dumps(bad_json))
        )
        provider = DeepSeekProvider(api_key="test-key")
        result = await provider.infer_profile_domain("test", "test", ["test"])
        assert result["domain"] == "unknown"
        assert result["suggested_keywords"] == []


# ---------------------------------------------------------------------------
# Ollama provider tests
# ---------------------------------------------------------------------------


def _ollama_response(content: str) -> httpx.Response:
    return httpx.Response(200, json={"response": content})


class TestOllamaProvider:
    @respx.mock
    async def test_extract_skills(self) -> None:
        respx.post("http://localhost:11434/api/generate").mock(
            return_value=_ollama_response(json.dumps(_EXTRACTED_JSON))
        )
        provider = OllamaProvider()
        result = await provider.extract_skills("Test job description about ML.")
        assert isinstance(result, ExtractedSkills)
        assert result.seniority == "senior"

    @respx.mock
    async def test_extract_skills_with_fenced_json(self) -> None:
        fenced = f"```json\n{json.dumps(_EXTRACTED_JSON)}\n```"
        respx.post("http://localhost:11434/api/generate").mock(
            return_value=_ollama_response(fenced)
        )
        provider = OllamaProvider()
        result = await provider.extract_skills("Test job description.")
        assert result.tecnologias == ["TensorFlow"]

    @respx.mock
    async def test_extract_recruiter_signals(self) -> None:
        respx.post("http://localhost:11434/api/generate").mock(
            return_value=_ollama_response(json.dumps(_RECRUITER_JSON))
        )
        provider = OllamaProvider()
        result = await provider.extract_recruiter_signals("Looking for an ML Engineer.")
        assert result["roles"] == ["ML Engineer"]

    @respx.mock
    async def test_suggest_portfolio(self) -> None:
        respx.post("http://localhost:11434/api/generate").mock(
            return_value=_ollama_response("## Project 1\nBuild an ML pipeline")
        )
        provider = OllamaProvider()
        result = await provider.suggest_portfolio(_make_stats(), _make_profile())
        assert "Project" in result

    @respx.mock
    async def test_infer_profile_domain(self) -> None:
        respx.post("http://localhost:11434/api/generate").mock(
            return_value=_ollama_response(json.dumps(_PROFILE_JSON))
        )
        provider = OllamaProvider()
        result = await provider.infer_profile_domain("ML Engineer", "Senior ML", ["Python"])
        assert result["domain"] == "AI/ML"

    @respx.mock
    async def test_health_check_success(self) -> None:
        respx.get("http://localhost:11434/api/tags").mock(
            return_value=httpx.Response(200, json={"models": []})
        )
        provider = OllamaProvider()
        assert await provider.health_check() is True

    @respx.mock
    async def test_health_check_failure(self) -> None:
        respx.get("http://localhost:11434/api/tags").mock(return_value=httpx.Response(500))
        provider = OllamaProvider()
        assert await provider.health_check() is False

    @respx.mock
    async def test_recruiter_signals_non_list_fallback(self) -> None:
        bad_json = {"roles": "not a list", "skills": 123}
        respx.post("http://localhost:11434/api/generate").mock(
            return_value=_ollama_response(json.dumps(bad_json))
        )
        provider = OllamaProvider()
        result = await provider.extract_recruiter_signals("test message")
        assert result["roles"] == []
        assert result["skills"] == []


# ---------------------------------------------------------------------------
# Anthropic provider tests
# ---------------------------------------------------------------------------


def _mock_anthropic_message(text: str) -> MagicMock:
    block = MagicMock()
    block.type = "text"
    block.text = text
    msg = MagicMock()
    msg.content = [block]
    return msg


class TestAnthropicProvider:
    async def test_extract_skills(self) -> None:
        with patch("linkedin_intelligence.providers.anthropic.anthropic") as mock_mod:
            mock_client = AsyncMock()
            mock_mod.AsyncAnthropic.return_value = mock_client
            mock_client.messages.create = AsyncMock(
                return_value=_mock_anthropic_message(json.dumps(_EXTRACTED_JSON))
            )

            from linkedin_intelligence.providers.anthropic import AnthropicProvider

            provider = AnthropicProvider(api_key="test-key")
            provider._client = mock_client
            result = await provider.extract_skills("Test job description.")
            assert isinstance(result, ExtractedSkills)
            assert result.industria == "AI"

    async def test_extract_recruiter_signals(self) -> None:
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            return_value=_mock_anthropic_message(json.dumps(_RECRUITER_JSON))
        )
        from linkedin_intelligence.providers.anthropic import AnthropicProvider

        provider = AnthropicProvider(api_key="test-key")
        provider._client = mock_client
        result = await provider.extract_recruiter_signals("Looking for ML Engineer.")
        assert result["roles"] == ["ML Engineer"]

    async def test_suggest_portfolio(self) -> None:
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            return_value=_mock_anthropic_message("## Project 1\nBuild pipeline")
        )
        from linkedin_intelligence.providers.anthropic import AnthropicProvider

        provider = AnthropicProvider(api_key="test-key")
        provider._client = mock_client
        result = await provider.suggest_portfolio(_make_stats(), _make_profile())
        assert "Project" in result

    async def test_infer_profile_domain(self) -> None:
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            return_value=_mock_anthropic_message(json.dumps(_PROFILE_JSON))
        )
        from linkedin_intelligence.providers.anthropic import AnthropicProvider

        provider = AnthropicProvider(api_key="test-key")
        provider._client = mock_client
        result = await provider.infer_profile_domain("ML Engineer", "Senior ML", ["Python"])
        assert result["domain"] == "AI/ML"

    async def test_health_check_success(self) -> None:
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=_mock_anthropic_message("pong"))
        from linkedin_intelligence.providers.anthropic import AnthropicProvider

        provider = AnthropicProvider(api_key="test-key")
        provider._client = mock_client
        assert await provider.health_check() is True

    async def test_health_check_failure(self) -> None:
        import anthropic as anthropic_mod

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            side_effect=anthropic_mod.APIError(
                message="test error",
                request=MagicMock(),
                body=None,
            )
        )
        from linkedin_intelligence.providers.anthropic import AnthropicProvider

        provider = AnthropicProvider(api_key="test-key")
        provider._client = mock_client
        assert await provider.health_check() is False

    async def test_extract_skills_with_fenced_json(self) -> None:
        fenced = f"```json\n{json.dumps(_EXTRACTED_JSON)}\n```"
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=_mock_anthropic_message(fenced))
        from linkedin_intelligence.providers.anthropic import AnthropicProvider

        provider = AnthropicProvider(api_key="test-key")
        provider._client = mock_client
        result = await provider.extract_skills("Test job.")
        assert result.skills_tecnicas == ["Python", "ML"]

    async def test_non_text_block_raises(self) -> None:
        block = MagicMock()
        block.type = "image"
        msg = MagicMock()
        msg.content = [block]

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=msg)

        from linkedin_intelligence.providers.anthropic import AnthropicProvider

        provider = AnthropicProvider(api_key="test-key")
        provider._client = mock_client
        with pytest.raises(ValueError, match="Unexpected block type"):
            await provider.extract_skills("test")

    async def test_recruiter_signals_non_list_fallback(self) -> None:
        bad_json = {"roles": "not a list", "skills": 123}
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            return_value=_mock_anthropic_message(json.dumps(bad_json))
        )
        from linkedin_intelligence.providers.anthropic import AnthropicProvider

        provider = AnthropicProvider(api_key="test-key")
        provider._client = mock_client
        result = await provider.extract_recruiter_signals("test")
        assert result["roles"] == []
        assert result["skills"] == []


# ---------------------------------------------------------------------------
# Factory tests
# ---------------------------------------------------------------------------


class TestGetProvider:
    def test_get_deepseek_provider(self) -> None:

        from pydantic import SecretStr

        from linkedin_intelligence.providers import get_provider

        settings = MagicMock()
        settings.llm_provider = "deepseek"
        settings.deepseek_api_key = SecretStr("test-key")
        settings.deepseek_model = "deepseek-chat"
        provider = get_provider(settings)
        assert type(provider).__name__ == "DeepSeekProvider"

    def test_get_ollama_provider(self) -> None:
        from linkedin_intelligence.providers import get_provider

        settings = MagicMock()
        settings.llm_provider = "ollama"
        settings.ollama_base_url = "http://localhost:11434"
        settings.ollama_model = "qwen2.5:7b"
        provider = get_provider(settings)
        assert type(provider).__name__ == "OllamaProvider"

    def test_get_anthropic_provider(self) -> None:
        from pydantic import SecretStr

        from linkedin_intelligence.providers import get_provider

        settings = MagicMock()
        settings.llm_provider = "anthropic"
        settings.anthropic_api_key = SecretStr("test-key")
        settings.anthropic_model = "claude-opus-4-5"
        provider = get_provider(settings)
        assert type(provider).__name__ == "AnthropicProvider"

    def test_unknown_provider_raises(self) -> None:
        from linkedin_intelligence.providers import get_provider

        settings = MagicMock()
        settings.llm_provider = "unknown"
        with pytest.raises(ValueError, match="Unknown LLM provider"):
            get_provider(settings)


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    def test_deepseek_is_llm_provider(self) -> None:
        from linkedin_intelligence.providers.base import LLMProvider

        assert isinstance(DeepSeekProvider(api_key="k"), LLMProvider)

    def test_ollama_is_llm_provider(self) -> None:
        from linkedin_intelligence.providers.base import LLMProvider

        assert isinstance(OllamaProvider(), LLMProvider)

    def test_anthropic_is_llm_provider(self) -> None:
        from linkedin_intelligence.providers.anthropic import AnthropicProvider
        from linkedin_intelligence.providers.base import LLMProvider

        assert isinstance(AnthropicProvider(api_key="k"), LLMProvider)
