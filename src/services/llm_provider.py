# LICENSE HEADER MANAGED BY add-license-header
#
# BSD 3-Clause License
#
# Copyright (c) 2026, Martin Vesterlund
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, this
#    list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
#
# 3. Neither the name of the copyright holder nor the names of its
#    contributors may be used to endorse or promote products derived from
#    this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#

"""Provider abstractions and schema validation helpers for LLM output.

The module is the central integration point for runtime LLM access. It defines:
- the provider interface used by the API layer
- configuration loading from ``config.yaml``
- concrete runtime providers such as Ollama
- validation wrappers that convert raw provider payloads into typed Pydantic
  models

To add a new provider, a developer typically needs to:
1. implement ``LLMProvider``
2. add a configuration section under ``llm_provider`` in ``config.yaml``
3. extend ``get_llm_provider()`` so the new provider can be selected
4. keep provider output schema-compatible so existing validation still works
"""

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from pydantic import ValidationError
import yaml

from src.models.session import SessionState
from src.schemas.interpreted_action import InterpretedAction
from src.schemas.narrator_response import NarratorResponse


PROMPTS_DIR = Path(__file__).resolve().parents[2] / "data" / "prompts"
CONFIG_PATH = Path(__file__).resolve().parents[2] / "config.yaml"


class LLMProviderError(Exception):
    """Base exception for provider-related failures."""

    pass


class ProviderOutputValidationError(LLMProviderError):
    """Raised when provider output cannot be validated against schemas."""

    pass


class ProviderConfigurationError(LLMProviderError):
    """Raised when provider configuration is unsupported or unavailable."""

    pass


class ProviderResponseFormatError(LLMProviderError):
    """Raised when provider text output cannot be parsed into JSON."""

    pass


class LLMProvider(ABC):
    """Abstract interface for action interpretation and narration providers.

    Every runtime provider must implement the same two operations:
    - ``interpret_action`` for transforming participant free text into a
      structured action payload
    - ``generate_narration`` for turning a session state into a structured
      narration payload

    The returned dictionaries are intentionally raw. They are validated later
    through Pydantic schemas so all providers share the same output contract.
    """

    @abstractmethod
    def interpret_action(self, participant_input: str) -> dict[str, Any]:
        """Interpret participant free text into structured action data.

        Args:
            participant_input: Free-text participant action to interpret.

        Returns:
            dict[str, Any]: Raw structured payload to validate as an
                ``InterpretedAction``.
        """

        raise NotImplementedError

    @abstractmethod
    def generate_narration(self, state: SessionState) -> dict[str, Any]:
        """Generate narration from a session state snapshot.

        Args:
            state: Session state after rules have been applied.

        Returns:
            dict[str, Any]: Raw structured payload to validate as a
                ``NarratorResponse``.
        """

        raise NotImplementedError


def load_prompt(name: str) -> str:
    """Load a prompt file from the prompt directory.

    Args:
        name: File name of the prompt to load.

    Returns:
        str: Prompt contents as UTF-8 text.

    Raises:
        FileNotFoundError: If the prompt file does not exist.
    """

    return (PROMPTS_DIR / name).read_text(encoding="utf-8").strip()


def load_config(path: Path | None = None) -> dict[str, Any]:
    """Load application configuration from ``config.yaml``.

    Args:
        path: Path to the YAML configuration file.

    Returns:
        dict[str, Any]: Parsed configuration document.

    Raises:
        ProviderConfigurationError: If the file is missing or invalid.
    """

    config_path = path or CONFIG_PATH

    if not config_path.exists():
        raise ProviderConfigurationError(f"Configuration file not found: {config_path}")

    try:
        with config_path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
    except yaml.YAMLError as exc:
        raise ProviderConfigurationError(
            f"Invalid YAML configuration in {config_path}"
        ) from exc

    if not isinstance(data, dict):
        raise ProviderConfigurationError(
            f"Configuration root must be a mapping in {config_path}"
        )

    return data


def load_llm_config(path: Path | None = None) -> dict[str, Any]:
    """Load the LLM-specific configuration section.

    Args:
        path: Path to the YAML configuration file.

    Returns:
        dict[str, Any]: LLM provider configuration mapping.

    Raises:
        ProviderConfigurationError: If the ``llm_provider`` section is missing.

    Notes:
        The expected structure is a top-level ``llm_provider`` mapping with a
        ``provider`` selector and one nested mapping per supported provider,
        for example ``ollama`` or ``openai``.
    """

    data = load_config(path)
    llm_config = data.get("llm_provider")

    if not isinstance(llm_config, dict):
        raise ProviderConfigurationError(
            "Missing or invalid llm_provider section in config.yaml"
        )

    return llm_config


def validate_interpreted_action(payload: dict[str, Any]) -> InterpretedAction:
    """Validate raw provider output as an interpreted action.

    Args:
        payload: Raw provider payload for action interpretation.

    Returns:
        InterpretedAction: Validated interpreted action.

    Raises:
        ProviderOutputValidationError: If the payload does not satisfy the
            action schema.
    """

    try:
        return InterpretedAction.model_validate(payload)
    except ValidationError as exc:
        raise ProviderOutputValidationError(
            "Invalid interpreted action payload"
        ) from exc


def validate_narration(payload: dict[str, Any]) -> NarratorResponse:
    """Validate raw provider output as a narration payload.

    Args:
        payload: Raw provider payload for narration generation.

    Returns:
        NarratorResponse: Validated narration payload.

    Raises:
        ProviderOutputValidationError: If the payload does not satisfy the
            narration schema.
    """

    try:
        return NarratorResponse.model_validate(payload)
    except ValidationError as exc:
        raise ProviderOutputValidationError("Invalid narration payload") from exc


class OllamaProvider(LLMProvider):
    """Runtime provider backed by the official Ollama Python client.

    The provider supports:
    - local Ollama via ``host: http://localhost:11434``
    - Ollama Cloud via ``host: https://ollama.com`` together with ``api_key``

    It requests JSON-only responses and parses them into Python dictionaries
    before schema validation happens in the API layer.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """Create an Ollama-backed runtime provider from config data.

        Args:
            config: Mapping from ``config.yaml`` under ``llm_provider.ollama``.
                Supported keys are ``host``, ``api_key``, ``model``,
                ``interpret_model`` and ``narration_model``.
        """

        self.interpret_prompt = load_prompt("interpret_action.txt")
        self.narration_prompt = load_prompt("generate_narration.txt")
        self.host = str(config.get("host") or "http://localhost:11434")
        self.default_model = str(config.get("model") or "llama3.2")
        self.interpret_model = str(config.get("interpret_model") or self.default_model)
        self.narration_model = str(config.get("narration_model") or self.default_model)
        self.api_key = config.get("api_key")
        self.client = self._create_client(self.host, self._build_headers())

    @staticmethod
    def _create_client(host: str, headers: dict[str, str] | None):
        """Create an Ollama client instance.

        Args:
            host: Base URL for the Ollama endpoint.
            headers: Optional headers applied to each request.

        Returns:
            Any: Instantiated Ollama client.

        Raises:
            ProviderConfigurationError: If the Ollama package is not installed.
        """

        try:
            from ollama import Client
        except ImportError as exc:
            raise ProviderConfigurationError(
                "The ollama package is required for OllamaProvider. Install it with pip install ollama."
            ) from exc

        return Client(host=host, headers=headers or None)

    def _build_headers(self) -> dict[str, str] | None:
        """Build optional authorization headers for Ollama requests.

        Returns:
            dict[str, str] | None: Authorization headers when an API key is
                configured, otherwise ``None``.
        """

        if not self.api_key:
            return None

        return {"Authorization": f"Bearer {self.api_key}"}

    @staticmethod
    def _extract_json_payload(response: Any) -> dict[str, Any]:
        """Extract and parse JSON content from an Ollama chat response.

        Args:
            response: Response object returned by the Ollama client.

        Returns:
            dict[str, Any]: Parsed JSON payload.

        Raises:
            ProviderResponseFormatError: If the response content is missing or
                cannot be parsed as a JSON object.
        """

        message = getattr(response, "message", None)
        if message is None and isinstance(response, dict):
            message = response.get("message")

        content = getattr(message, "content", None) if message is not None else None
        if content is None and isinstance(message, dict):
            content = message.get("content")

        if not isinstance(content, str) or not content.strip():
            raise ProviderResponseFormatError(
                "Ollama response did not contain message content"
            )

        stripped = content.strip()
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            start = stripped.find("{")
            end = stripped.rfind("}")
            if start == -1 or end == -1 or end <= start:
                raise ProviderResponseFormatError(
                    "Ollama response was not valid JSON"
                ) from None

            try:
                parsed = json.loads(stripped[start : end + 1])
            except json.JSONDecodeError as exc:
                raise ProviderResponseFormatError(
                    "Ollama response was not valid JSON"
                ) from exc

        if not isinstance(parsed, dict):
            raise ProviderResponseFormatError("Ollama response JSON must be an object")

        return parsed

    def _chat_json(
        self, model: str, system_prompt: str, user_prompt: str
    ) -> dict[str, Any]:
        """Send a chat request and parse the returned JSON object.

        Args:
            model: Ollama model name to use.
            system_prompt: System instruction describing the task and format.
            user_prompt: User-specific request content.

        Returns:
            dict[str, Any]: Parsed JSON payload returned by the model.

        Raises:
            LLMProviderError: If the Ollama request fails.
            ProviderResponseFormatError: If the response content is not JSON.
        """

        try:
            response = self.client.chat(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
        except Exception as exc:
            raise LLMProviderError(f"Ollama request failed: {exc}") from exc

        return self._extract_json_payload(response)

    def interpret_action(self, participant_input: str) -> dict[str, Any]:
        """Interpret participant text via Ollama.

        Args:
            participant_input: Free-text participant action.

        Returns:
            dict[str, Any]: Raw payload intended for ``InterpretedAction``.

        Raises:
            LLMProviderError: If the Ollama request fails.
            ProviderResponseFormatError: If the model does not return JSON.
        """

        expected_shape = {
            "action_summary": "string",
            "action_types": [
                "containment|coordination|communication|escalation|analysis|recovery|monitoring|legal|business_continuity"
            ],
            "targets": ["string"],
            "intent": "string",
            "expected_effects": ["string"],
            "risks": ["string"],
            "uncertainties": ["string"],
            "priority": "low|medium|high",
            "confidence": "number between 0 and 1",
        }
        return self._chat_json(
            model=self.interpret_model,
            system_prompt=(
                f"{self.interpret_prompt}\n"
                "Return only a single JSON object and no surrounding prose.\n"
                f"Expected shape: {json.dumps(expected_shape, ensure_ascii=True)}"
            ),
            user_prompt=f"Deltagaratgard:\n{participant_input}",
        )

    def generate_narration(self, state: SessionState) -> dict[str, Any]:
        """Generate a narrated situation update via Ollama.

        Args:
            state: Session state after deterministic rules have been applied.

        Returns:
            dict[str, Any]: Raw payload intended for ``NarratorResponse``.

        Raises:
            LLMProviderError: If the Ollama request fails.
            ProviderResponseFormatError: If the model does not return JSON.
        """

        expected_shape = {
            "situation_update": "string",
            "key_points": ["string"],
            "new_consequences": ["string"],
            "injects": [
                {
                    "type": "media|executive|operations|technical|stakeholder",
                    "title": "string",
                    "message": "string",
                }
            ],
            "decisions_to_consider": ["string"],
            "facilitator_notes": "string",
        }
        return self._chat_json(
            model=self.narration_model,
            system_prompt=(
                f"{self.narration_prompt}\n"
                "Return only a single JSON object and no surrounding prose.\n"
                f"Expected shape: {json.dumps(expected_shape, ensure_ascii=True)}"
            ),
            user_prompt=f"Session state:\n{state.model_dump_json()}",
        )


class OpenAIProvider(LLMProvider):
    """Stub implementation for a future OpenAI-backed provider.

    The class currently loads prompt files but intentionally raises a
    configuration error when called because external integration is not yet
    implemented in this project.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """Create an OpenAI provider stub from config data.

        Args:
            config: Mapping from ``config.yaml`` under ``llm_provider.openai``.
                The values are currently stored for future use only.
        """

        self.interpret_prompt = load_prompt("interpret_action.txt")
        self.narration_prompt = load_prompt("generate_narration.txt")
        self.config = config or {}

    def interpret_action(self, participant_input: str) -> dict[str, Any]:
        """Attempt to interpret an action with the OpenAI provider.

        Args:
            participant_input: Free-text participant action.

        Returns:
            dict[str, Any]: Never returns while the provider is stubbed.

        Raises:
            ProviderConfigurationError: Always, because the provider is not yet
                implemented.
        """

        raise ProviderConfigurationError("OpenAIProvider is not implemented yet")

    def generate_narration(self, state: SessionState) -> dict[str, Any]:
        """Attempt to generate narration with the OpenAI provider.

        Args:
            state: Session state to narrate.

        Returns:
            dict[str, Any]: Never returns while the provider is stubbed.

        Raises:
            ProviderConfigurationError: Always, because the provider is not yet
                implemented.
        """

        raise ProviderConfigurationError("OpenAIProvider is not implemented yet")


def get_llm_provider() -> LLMProvider:
    """Create the configured runtime provider instance.

    The provider is selected from ``config.yaml`` by reading
    ``llm_provider.provider`` and then the matching nested provider section.

    Returns:
        LLMProvider: Configured provider instance.

    Raises:
        ProviderConfigurationError: If the configured provider name is not
            supported.

    Notes:
        To add a new provider, extend this factory with a new branch and define
        a matching configuration block in ``config.yaml``.
    """

    llm_config = load_llm_config()
    provider_name = str(llm_config.get("provider") or "ollama").lower()

    if provider_name == "ollama":
        provider_config = llm_config.get("ollama")
        if not isinstance(provider_config, dict):
            raise ProviderConfigurationError(
                "Missing or invalid llm_provider.ollama section in config.yaml"
            )
        return OllamaProvider(provider_config)

    if provider_name == "openai":
        provider_config = llm_config.get("openai")
        if provider_config is not None and not isinstance(provider_config, dict):
            raise ProviderConfigurationError(
                "Invalid llm_provider.openai section in config.yaml"
            )
        return OpenAIProvider(provider_config)

    raise ProviderConfigurationError(f"Unsupported LLM provider: {provider_name}")
