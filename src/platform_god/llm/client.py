"""
LLM Client - unified interface for multiple LLM providers.

Supports Anthropic Claude, OpenAI GPT, and compatible APIs.
"""

import json
import os
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from platform_god.core.exceptions import (
    ConfigurationError,
    LLMError,
    LLMAuthenticationError,
    LLMRateLimitError,
)


class LLMProvider(Enum):
    """Supported LLM providers."""

    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    AZURE_OPENAI = "azure_openai"
    CUSTOM = "custom"


@dataclass
class LLMRequest:
    """Request to an LLM."""

    prompt: str
    system_prompt: str | None = None
    max_tokens: int = 4096
    temperature: float = 0.0
    response_format: str | None = None  # "json" for strict JSON output


@dataclass
class LLMResponse:
    """Response from an LLM."""

    content: str
    model: str
    provider: LLMProvider
    tokens_used: int | None = None
    finish_reason: str | None = None
    raw_response: dict[str, Any] = field(default_factory=dict)

    def parse_json(self) -> dict[str, Any] | None:
        """Parse response content as JSON."""
        try:
            return json.loads(self.content)
        except json.JSONDecodeError:
            # Try to extract JSON from markdown code block
            if "```json" in self.content:
                try:
                    start = self.content.index("```json") + 7
                    end = self.content.index("```", start)
                    return json.loads(self.content[start:end].strip())
                except (ValueError, json.JSONDecodeError):
                    pass
            elif "```" in self.content:
                try:
                    start = self.content.index("```") + 3
                    end = self.content.index("```", start)
                    return json.loads(self.content[start:end].strip())
                except (ValueError, json.JSONDecodeError):
                    pass
            return None


class LLMConfig(BaseModel):
    """Configuration for LLM client."""

    provider: LLMProvider = LLMProvider.ANTHROPIC
    api_key: str = ""
    base_url: str | None = None
    model: str = "claude-3-5-sonnet-20241022"
    timeout_seconds: int = 120


class LLMClient:
    """
    Unified LLM client supporting multiple providers.

    Environment variables:
    - ANTHROPIC_API_KEY: For Claude models
    - OPENAI_API_KEY: For OpenAI models
    - PG_LLM_PROVIDER: Override provider (anthropic|openai)
    - PG_LLM_MODEL: Override model name
    - PG_LLM_BASE_URL: Custom base URL
    """

    DEFAULT_MODELS = {
        LLMProvider.ANTHROPIC: "claude-3-5-sonnet-20241022",
        LLMProvider.OPENAI: "gpt-4o",
        LLMProvider.AZURE_OPENAI: "gpt-4o",
        LLMProvider.CUSTOM: "custom-model",
    }

    def __init__(self, config: LLMConfig | None = None):
        """Initialize LLM client with configuration."""
        self._config = config or self._load_config()
        self._client = httpx.Client(timeout=self._config.timeout_seconds)

    @staticmethod
    def _load_config() -> LLMConfig:
        """Load configuration from environment."""
        provider_str = os.getenv("PG_LLM_PROVIDER", "anthropic")
        try:
            provider = LLMProvider(provider_str)
        except ValueError:
            provider = LLMProvider.ANTHROPIC

        api_key = ""
        if provider == LLMProvider.ANTHROPIC:
            api_key = os.getenv("ANTHROPIC_API_KEY", "")
        elif provider in (LLMProvider.OPENAI, LLMProvider.AZURE_OPENAI):
            api_key = os.getenv("OPENAI_API_KEY", "")
        else:
            api_key = os.getenv("PG_LLM_API_KEY", "")

        model = os.getenv("PG_LLM_MODEL", LLMClient.DEFAULT_MODELS[provider])
        base_url = os.getenv("PG_LLM_BASE_URL")

        return LLMConfig(
            provider=provider,
            api_key=api_key,
            base_url=base_url,
            model=model,
        )

    @property
    def provider(self) -> LLMProvider:
        """Get the LLM provider."""
        return self._config.provider

    @property
    def model(self) -> str:
        """Get the model name."""
        return self._config.model

    def complete(self, request: LLMRequest) -> LLMResponse:
        """
        Send a completion request to the LLM.

        Args:
            request: LLM request with prompt and parameters

        Returns:
            LLMResponse with content and metadata

        Raises:
            LLMAuthenticationError: If API key is invalid
            LLMRateLimitError: If rate limit is exceeded after retries
            LLMError: For other LLM-related errors
        """
        if not self._config.api_key:
            raise LLMAuthenticationError(
                f"API key not configured for {self._config.provider.value}. "
                f"Set {self._get_api_key_env_var()} environment variable.",
                provider=self._config.provider.value,
            )

        try:
            return self._complete_with_retry(request)
        except httpx.HTTPStatusError as e:
            self._handle_http_error(e)
        except httpx.HTTPError as e:
            raise LLMError(
                f"HTTP error during LLM request: {e}",
                provider=self._config.provider.value,
                model=self._config.model,
            )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        retry=retry_if_exception_type(httpx.HTTPStatusError),
        reraise=True,
    )
    def _complete_with_retry(self, request: LLMRequest) -> LLMResponse:
        """
        Execute completion with retry logic using tenacity.

        Retries on:
        - 429 (rate limit)
        - 502, 503, 504 (server errors)
        - Connection errors

        Uses exponential backoff with jitter.
        """
        try:
            if self._config.provider == LLMProvider.ANTHROPIC:
                return self._anthropic_complete(request)
            elif self._config.provider == LLMProvider.OPENAI:
                return self._openai_complete(request)
            else:
                return self._openai_complete(request)  # Compatible API
        except httpx.HTTPStatusError as e:
            # Only retry on specific status codes
            if e.response.status_code in (429, 502, 503, 504):
                # Let tenacity handle retry
                raise
            # Don't retry on client errors (4xx except 429)
            self._handle_http_error(e)

    def _handle_http_error(self, error: httpx.HTTPStatusError) -> None:
        """Convert HTTP errors to appropriate LLM exceptions."""
        status_code = error.response.status_code
        provider = self._config.provider.value

        if status_code == 401:
            raise LLMAuthenticationError(
                f"Authentication failed for {provider}",
                provider=provider,
            )
        elif status_code == 429:
            raise LLMRateLimitError(
                f"Rate limit exceeded for {provider}",
                provider=provider,
            )
        elif status_code >= 500:
            raise LLMError(
                f"Server error from {provider}: {status_code}",
                provider=provider,
                model=self._config.model,
                status_code=status_code,
            )
        else:
            raise LLMError(
                f"HTTP error from {provider}: {status_code}",
                provider=provider,
                model=self._config.model,
                status_code=status_code,
            )

    def _anthropic_complete(self, request: LLMRequest) -> LLMResponse:
        """Complete using Anthropic's API."""
        headers = {
            "x-api-key": self._config.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        body = {
            "model": self._config.model,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "messages": [{"role": "user", "content": request.prompt}],
        }

        if request.system_prompt:
            body["system"] = request.system_prompt

        url = self._config.base_url or "https://api.anthropic.com/v1/messages"

        response = self._client.post(url, headers=headers, json=body)
        response.raise_for_status()
        data = response.json()

        return LLMResponse(
            content=data["content"][0]["text"],
            model=data["model"],
            provider=LLMProvider.ANTHROPIC,
            tokens_used=data.get("usage", {}).get("input_tokens", 0)
            + data.get("usage", {}).get("output_tokens", 0),
            finish_reason=data.get("stop_reason"),
            raw_response=data,
        )

    def _openai_complete(self, request: LLMRequest) -> LLMResponse:
        """Complete using OpenAI's API (or compatible)."""
        headers = {
            "Authorization": f"Bearer {self._config.api_key}",
            "content-type": "application/json",
        }

        messages = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        messages.append({"role": "user", "content": request.prompt})

        body = {
            "model": self._config.model,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "messages": messages,
        }

        if request.response_format == "json":
            body["response_format"] = {"type": "json_object"}

        url = self._config.base_url or "https://api.openai.com/v1/chat/completions"

        response = self._client.post(url, headers=headers, json=body)
        response.raise_for_status()
        data = response.json()

        return LLMResponse(
            content=data["choices"][0]["message"]["content"],
            model=data["model"],
            provider=self._config.provider,
            tokens_used=data.get("usage", {}).get("total_tokens"),
            finish_reason=data["choices"][0].get("finish_reason"),
            raw_response=data,
        )

    def _get_api_key_env_var(self) -> str:
        """Get the environment variable name for the API key."""
        if self._config.provider == LLMProvider.ANTHROPIC:
            return "ANTHROPIC_API_KEY"
        elif self._config.provider in (LLMProvider.OPENAI, LLMProvider.AZURE_OPENAI):
            return "OPENAI_API_KEY"
        return "PG_LLM_API_KEY"

    def close(self) -> None:
        """Close the HTTP client."""
        self._client.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, *args):
        """Context manager exit."""
        self.close()


@lru_cache(maxsize=1)
def get_default_client() -> LLMClient:
    """Get the default LLM client (cached)."""
    return LLMClient()


def load_agent_prompt(agent_name: str, agents_dir: Path | None = None) -> str:
    """
    Load an agent's prompt from its markdown file.

    Args:
        agent_name: Name of the agent (without _AGENT suffix)
        agents_dir: Directory containing agent prompts

    Returns:
        Full agent prompt text

    Raises:
        ConfigurationError: If agent prompt file is not found
    """
    if agents_dir is None:
        # Find agents directory relative to this file
        here = Path(__file__).parent
        root = here.parent.parent.parent
        agents_dir = root / "prompts" / "agents"

    agent_file = agents_dir / f"{agent_name}_AGENT.md"
    if not agent_file.exists():
        raise ConfigurationError(
            f"Agent prompt not found: {agent_file}",
            config_file=str(agent_file),
            details={"agent_name": agent_name, "searched_path": str(agents_dir)},
        )

    content = agent_file.read_text()

    # Extract the text content from the code block
    if content.startswith("```text"):
        content = content.split("```text")[1].split("```")[0].strip()
    elif content.startswith("```"):
        content = content.split("```", 2)[2] if "```" in content[6:] else content

    return content.strip()


def format_agent_prompt(prompt_template: str, input_data: dict[str, Any]) -> str:
    """
    Format an agent prompt with input data.

    Args:
        prompt_template: Raw agent prompt template
        input_data: Input values to substitute

    Returns:
        Formatted prompt with inputs appended
    """
    # Build the input section
    input_lines = ["\nINPUT VALUES:"]
    for key, value in input_data.items():
        if isinstance(value, (dict, list)):
            value_str = json.dumps(value, indent=2)
        else:
            value_str = str(value)
        input_lines.append(f"- {key}: {value_str}")

    return f"{prompt_template}\n\n{''.join(input_lines)}"
