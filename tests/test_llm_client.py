"""Tests for LLM client module."""

from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
import httpx

from platform_god.core.exceptions import ConfigurationError, LLMAuthenticationError
from platform_god.llm.client import (
    LLMClient,
    LLMConfig,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    format_agent_prompt,
    get_default_client,
    load_agent_prompt,
)


class TestLLMProvider:
    """Tests for LLMProvider enum."""

    def test_all_providers_defined(self) -> None:
        """All expected providers are defined."""
        expected = {"anthropic", "openai", "azure_openai", "custom"}
        actual = {lp.value for lp in LLMProvider}
        assert actual == expected


class TestLLMRequest:
    """Tests for LLMRequest dataclass."""

    def test_minimal_request(self) -> None:
        """LLMRequest can be created with minimal parameters."""
        req = LLMRequest(prompt="Test prompt")
        assert req.prompt == "Test prompt"
        assert req.system_prompt is None
        assert req.max_tokens == 4096
        assert req.temperature == 0.0

    def test_full_request(self) -> None:
        """LLMRequest can have all fields specified."""
        req = LLMRequest(
            prompt="Test prompt",
            system_prompt="System instructions",
            max_tokens=2048,
            temperature=0.5,
            response_format="json",
        )
        assert req.prompt == "Test prompt"
        assert req.system_prompt == "System instructions"
        assert req.max_tokens == 2048
        assert req.temperature == 0.5
        assert req.response_format == "json"


class TestLLMResponse:
    """Tests for LLMResponse dataclass."""

    def test_response_creation(self) -> None:
        """LLMResponse can be created."""
        resp = LLMResponse(
            content="Test response",
            model="claude-3-5-sonnet-20241022",
            provider=LLMProvider.ANTHROPIC,
        )
        assert resp.content == "Test response"
        assert resp.model == "claude-3-5-sonnet-20241022"
        assert resp.provider == LLMProvider.ANTHROPIC

    def test_parse_json_valid(self) -> None:
        """LLMResponse can parse valid JSON."""
        resp = LLMResponse(
            content='{"key": "value"}',
            model="claude-3-5-sonnet-20241022",
            provider=LLMProvider.ANTHROPIC,
        )
        result = resp.parse_json()
        assert result == {"key": "value"}

    def test_parse_json_invalid(self) -> None:
        """LLMResponse returns None for invalid JSON."""
        resp = LLMResponse(
            content="not json",
            model="claude-3-5-sonnet-20241022",
            provider=LLMProvider.ANTHROPIC,
        )
        result = resp.parse_json()
        assert result is None

    def test_parse_json_from_markdown_code_block(self) -> None:
        """LLMResponse can extract JSON from markdown code block."""
        resp = LLMResponse(
            content='```json\n{"key": "value"}\n```',
            model="claude-3-5-sonnet-20241022",
            provider=LLMProvider.ANTHROPIC,
        )
        result = resp.parse_json()
        assert result == {"key": "value"}

    def test_parse_json_from_plain_code_block(self) -> None:
        """LLMResponse can extract JSON from plain code block."""
        resp = LLMResponse(
            content='```\n{"key": "value"}\n```',
            model="claude-3-5-sonnet-20241022",
            provider=LLMProvider.ANTHROPIC,
        )
        result = resp.parse_json()
        assert result == {"key": "value"}

    def test_parse_json_with_surrounding_text(self) -> None:
        """LLMResponse can extract JSON from text with surrounding content."""
        resp = LLMResponse(
            content='Here is the result:\n```json\n{"key": "value"}\n```\nDone.',
            model="claude-3-5-sonnet-20241022",
            provider=LLMProvider.ANTHROPIC,
        )
        result = resp.parse_json()
        assert result == {"key": "value"}


class TestLLMConfig:
    """Tests for LLMConfig model."""

    def test_default_config(self) -> None:
        """LLMConfig has sensible defaults."""
        config = LLMConfig()
        assert config.provider == LLMProvider.ANTHROPIC
        assert config.api_key == ""
        assert config.model == "claude-3-5-sonnet-20241022"
        assert config.timeout_seconds == 120

    def test_custom_config(self) -> None:
        """LLMConfig can be customized."""
        config = LLMConfig(
            provider=LLMProvider.OPENAI,
            api_key="test-key",
            model="gpt-4o",
            timeout_seconds=60,
        )
        assert config.provider == LLMProvider.OPENAI
        assert config.api_key == "test-key"
        assert config.model == "gpt-4o"
        assert config.timeout_seconds == 60


class TestLLMClient:
    """Tests for LLMClient class."""

    def test_default_models(self) -> None:
        """DEFAULT_MODELS dict has all providers."""
        assert LLMProvider.ANTHROPIC in LLMClient.DEFAULT_MODELS
        assert LLMProvider.OPENAI in LLMClient.DEFAULT_MODELS
        assert LLMProvider.AZURE_OPENAI in LLMClient.DEFAULT_MODELS
        assert LLMProvider.CUSTOM in LLMClient.DEFAULT_MODELS

    def test_initialization_with_default_config(self) -> None:
        """LLMClient initializes with default config."""
        client = LLMClient()
        assert client.provider == LLMProvider.ANTHROPIC
        assert client.model == "claude-3-5-sonnet-20241022"

    def test_initialization_with_custom_config(self) -> None:
        """LLMClient can use custom config."""
        config = LLMConfig(
            provider=LLMProvider.OPENAI,
            api_key="test-key",
            model="gpt-4o",
        )
        client = LLMClient(config=config)
        assert client.provider == LLMProvider.OPENAI
        assert client.model == "gpt-4o"

    def test_provider_property(self) -> None:
        """Provider property returns current provider."""
        config = LLMConfig(provider=LLMProvider.CUSTOM)
        client = LLMClient(config=config)
        assert client.provider == LLMProvider.CUSTOM

    def test_model_property(self) -> None:
        """Model property returns current model."""
        config = LLMConfig(model="custom-model")
        client = LLMClient(config=config)
        assert client.model == "custom-model"

    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
    @patch("platform_god.llm.client.httpx.Client")
    def test_complete_anthropic_success(self, mock_client_class: MagicMock) -> None:
        """Complete successfully calls Anthropic API."""
        # Mock the HTTP response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "content": [{"text": "Test response"}],
            "model": "claude-3-5-sonnet-20241022",
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 20},
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client_class.return_value = mock_client

        config = LLMConfig(provider=LLMProvider.ANTHROPIC, api_key="test-key")
        client = LLMClient(config=config)

        request = LLMRequest(prompt="Test")
        response = client.complete(request)

        assert response.content == "Test response"
        assert response.provider == LLMProvider.ANTHROPIC
        assert response.tokens_used == 30

    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
    @patch("platform_god.llm.client.httpx.Client")
    def test_complete_openai_success(self, mock_client_class: MagicMock) -> None:
        """Complete successfully calls OpenAI API."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {"content": "Test response"},
                    "finish_reason": "stop",
                }
            ],
            "model": "gpt-4o",
            "usage": {"total_tokens": 50},
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client_class.return_value = mock_client

        config = LLMConfig(provider=LLMProvider.OPENAI, api_key="test-key")
        client = LLMClient(config=config)

        request = LLMRequest(prompt="Test")
        response = client.complete(request)

        assert response.content == "Test response"
        assert response.provider == LLMProvider.OPENAI
        assert response.tokens_used == 50

    def test_complete_no_api_key(self) -> None:
        """Complete raises LLMAuthenticationError when no API key is configured."""
        config = LLMConfig(provider=LLMProvider.ANTHROPIC, api_key="")
        client = LLMClient(config=config)

        request = LLMRequest(prompt="Test")
        with pytest.raises(LLMAuthenticationError, match="API key not configured"):
            client.complete(request)

    @patch("platform_god.llm.client.httpx.Client")
    def test_close(self, mock_client_class: MagicMock) -> None:
        """Close closes the HTTP client."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        client = LLMClient()
        client.close()

        mock_client.close.assert_called_once()

    @patch("platform_god.llm.client.httpx.Client")
    def test_context_manager(self, mock_client_class: MagicMock) -> None:
        """Client can be used as context manager."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        with LLMClient() as client:
            assert client is not None

        mock_client.close.assert_called_once()

    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
    @patch("platform_god.llm.client.httpx.Client")
    def test_complete_with_system_prompt(self, mock_client_class: MagicMock) -> None:
        """Complete includes system prompt in request."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "content": [{"text": "Response"}],
            "model": "claude-3-5-sonnet-20241022",
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 20},
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client_class.return_value = mock_client

        config = LLMConfig(provider=LLMProvider.ANTHROPIC, api_key="test-key")
        client = LLMClient(config=config)

        request = LLMRequest(
            prompt="Test",
            system_prompt="System instructions",
        )
        client.complete(request)

        # Verify system prompt was included
        call_args = mock_client.post.call_args
        body = call_args.kwargs["json"]
        assert body["system"] == "System instructions"

    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
    @patch("platform_god.llm.client.httpx.Client")
    def test_complete_with_json_response_format(self, mock_client_class: MagicMock) -> None:
        """Complete includes JSON response format for OpenAI."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {"content": '{"result": "value"}'},
                    "finish_reason": "stop",
                }
            ],
            "model": "gpt-4o",
            "usage": {"total_tokens": 30},
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client_class.return_value = mock_client

        config = LLMConfig(provider=LLMProvider.OPENAI, api_key="test-key")
        client = LLMClient(config=config)

        request = LLMRequest(prompt="Test", response_format="json")
        client.complete(request)

        # Verify response format was included
        call_args = mock_client.post.call_args
        body = call_args.kwargs["json"]
        assert body["response_format"] == {"type": "json_object"}

    @patch.dict("os.environ", {"PG_LLM_PROVIDER": "openai", "OPENAI_API_KEY": "test-key"})
    def test_load_config_from_env(self) -> None:
        """Config is loaded from environment variables."""
        client = LLMClient()
        assert client.provider == LLMProvider.OPENAI
        assert client.model == "gpt-4o"

    @patch.dict("os.environ", {"PG_LLM_PROVIDER": "invalid", "ANTHROPIC_API_KEY": "test-key"})
    def test_load_config_invalid_provider_fallback(self) -> None:
        """Invalid provider falls back to Anthropic."""
        client = LLMClient()
        assert client.provider == LLMProvider.ANTHROPIC

    @patch.dict("os.environ", {"PG_LLM_PROVIDER": "custom", "PG_LLM_API_KEY": "test-key"})
    def test_load_config_custom_provider(self) -> None:
        """Custom provider uses PG_LLM_API_KEY."""
        config = LLMClient._load_config()
        assert config.provider == LLMProvider.CUSTOM
        assert config.api_key == "test-key"

    def test_get_api_key_env_var(self) -> None:
        """Get correct env var name for each provider."""
        config_anthropic = LLMConfig(provider=LLMProvider.ANTHROPIC)
        client = LLMClient(config=config_anthropic)
        assert client._get_api_key_env_var() == "ANTHROPIC_API_KEY"

        config_openai = LLMConfig(provider=LLMProvider.OPENAI)
        client = LLMClient(config=config_openai)
        assert client._get_api_key_env_var() == "OPENAI_API_KEY"

        config_azure = LLMConfig(provider=LLMProvider.AZURE_OPENAI)
        client = LLMClient(config=config_azure)
        assert client._get_api_key_env_var() == "OPENAI_API_KEY"

        config_custom = LLMConfig(provider=LLMProvider.CUSTOM)
        client = LLMClient(config=config_custom)
        assert client._get_api_key_env_var() == "PG_LLM_API_KEY"

    def test_get_default_client_cached(self) -> None:
        """get_default_client returns cached instance."""
        # Clear cache first to ensure clean state
        get_default_client.cache_clear()

        c1 = get_default_client()
        c2 = get_default_client()
        # Should be the same instance due to lru_cache
        assert c1 is c2


class TestLoadAgentPrompt:
    """Tests for load_agent_prompt function."""

    def test_load_prompt_success(self) -> None:
        """load_agent_prompt loads agent prompt from file."""
        # This test uses the actual prompts directory
        prompt = load_agent_prompt("PG_DISCOVERY")
        assert prompt  # Should have content
        assert "ROLE" in prompt or "You are" in prompt

    def test_load_prompt_not_found(self) -> None:
        """load_agent_prompt raises ConfigurationError for missing agent."""
        with pytest.raises(ConfigurationError, match="Agent prompt not found"):
            load_agent_prompt("NONEXISTENT_AGENT")

    def test_load_prompt_strips_code_block(self) -> None:
        """load_agent_prompt strips ```text code block wrapper."""
        # The actual agent files should have the content extracted
        prompt = load_agent_prompt("PG_DISCOVERY")
        # Should not start with ```text
        assert not prompt.startswith("```text")
        # Should not start with ``` at all
        assert not prompt.startswith("```")

    def test_load_prompt_custom_dir(self, temp_dir: Path) -> None:
        """load_agent_prompt can load from custom directory."""
        agents_dir = temp_dir / "agents"
        agents_dir.mkdir()
        agent_file = agents_dir / "TEST_AGENT.md"
        agent_file.write_text("```text\nTest prompt content\n```")

        prompt = load_agent_prompt("TEST", agents_dir=agents_dir)
        assert prompt == "Test prompt content"


class TestFormatAgentPrompt:
    """Tests for format_agent_prompt function."""

    def test_format_with_no_input(self) -> None:
        """format_agent_prompt adds INPUT VALUES section."""
        template = "You are an agent."
        result = format_agent_prompt(template, {})
        assert "INPUT VALUES:" in result
        assert "You are an agent." in result

    def test_format_with_string_input(self) -> None:
        """format_agent_prompt formats string input."""
        template = "You are an agent."
        result = format_agent_prompt(template, {"key": "value"})
        assert "INPUT VALUES:" in result
        assert "- key: value" in result

    def test_format_with_dict_input(self) -> None:
        """format_agent_prompt formats dict input as JSON."""
        template = "You are an agent."
        result = format_agent_prompt(template, {"nested": {"key": "value"}})
        assert "INPUT VALUES:" in result
        assert "- nested:" in result

    def test_format_with_list_input(self) -> None:
        """format_agent_prompt formats list input as JSON."""
        template = "You are an agent."
        result = format_agent_prompt(template, {"items": [1, 2, 3]})
        assert "INPUT VALUES:" in result
        assert "- items:" in result

    def test_format_preserves_template(self) -> None:
        """format_agent_prompt preserves original template."""
        template = "You are a TEST agent.\n\nDo things."
        result = format_agent_prompt(template, {"key": "value"})
        assert result.startswith(template)

    def test_format_with_multiple_inputs(self) -> None:
        """format_agent_prompt formats multiple input values."""
        template = "Agent template"
        result = format_agent_prompt(
            template,
            {"repo": "/path", "mode": "dry_run", "count": 5},
        )
        assert "- repo: /path" in result
        assert "- mode: dry_run" in result
        assert "- count: 5" in result
