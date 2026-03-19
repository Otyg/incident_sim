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

"""Provider abstractions, configuration loading and validation helpers.

Runtime provider implementations live under ``src.services.providers`` while
this module owns the shared interface, configuration loading, response
validation and provider selection factory.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from pydantic import ValidationError
import yaml

from src.logging_utils import get_logger
from src.models.scenario import Scenario
from src.models.session import SessionState
from src.models.turn import Turn
from src.schemas.debrief_response import DebriefResponse
from src.schemas.interpreted_action import InterpretedAction
from src.schemas.narrator_response import NarratorResponse
from src.services.scenario_draft_normalizer import normalize_scenario_payload


PROMPTS_DIR = Path(__file__).resolve().parents[2] / "data" / "prompts"
CONFIG_PATH = Path(__file__).resolve().parents[2] / "config.yaml"
logger = get_logger(__name__)


class LLMProviderError(Exception):
    """Base exception for provider-related failures."""

    pass


class ProviderUpstreamError(LLMProviderError):
    """Raised when an upstream LLM provider request fails."""

    def __init__(
        self,
        message: str,
        *,
        provider_stage: str,
        upstream_status_code: int | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.provider_stage = provider_stage
        self.upstream_status_code = upstream_status_code
        self.retryable = retryable


class ProviderOutputValidationError(LLMProviderError):
    """Raised when provider output cannot be validated against schemas."""

    pass


class ProviderConfigurationError(LLMProviderError):
    """Raised when provider configuration is unsupported or unavailable."""

    pass


class ProviderResponseFormatError(LLMProviderError):
    """Raised when provider text output cannot be parsed into JSON."""

    def __init__(
        self,
        message: str,
        *,
        provider_stage: str | None = None,
        raw_response_excerpt: str | None = None,
        retryable: bool = True,
    ) -> None:
        super().__init__(message)
        self.provider_stage = provider_stage
        self.raw_response_excerpt = raw_response_excerpt
        self.retryable = retryable


class LLMProvider(ABC):
    """Abstract interface for providers that produce structured LLM output."""

    @abstractmethod
    def interpret_action(self, participant_input: str) -> dict[str, Any]:
        """Interpret participant free text into structured action data."""

        raise NotImplementedError

    @abstractmethod
    def generate_narration(self, state: SessionState) -> dict[str, Any]:
        """Generate narration from a session state snapshot."""

        raise NotImplementedError

    @abstractmethod
    def generate_debrief(
        self, scenario: Scenario, state: SessionState, timeline: list[Turn]
    ) -> dict[str, Any]:
        """Generate a debrief from scenario, final state and timeline."""

        raise NotImplementedError

    @abstractmethod
    def generate_scenario_draft(
        self, source_text: str, source_format: str = "markdown"
    ) -> dict[str, Any]:
        """Generate a scenario draft from author-provided source text."""

        raise NotImplementedError


def load_prompt(name: str) -> str:
    """Load a prompt file from the prompt directory."""

    return (PROMPTS_DIR / name).read_text(encoding="utf-8").strip()


def load_prompt_bundle(config: dict[str, Any] | None = None) -> dict[str, str]:
    """Load configured prompt files with sensible defaults."""

    prompt_config = {}
    if isinstance(config, dict):
        raw_prompt_config = config.get("prompts")
        if raw_prompt_config is not None and not isinstance(raw_prompt_config, dict):
            raise ProviderConfigurationError(
                "Provider prompts configuration must be a mapping"
            )
        prompt_config = raw_prompt_config or {}

    prompt_files = {
        "interpret_prompt": str(
            prompt_config.get("interpret") or "interpret_action.txt"
        ),
        "narration_prompt": str(
            prompt_config.get("narration") or "generate_narration.txt"
        ),
        "debrief_prompt": str(prompt_config.get("debrief") or "generate_debrief.txt"),
        "scenario_authoring_prompt": str(
            prompt_config.get("scenario_authoring") or "generate_scenario_draft.txt"
        ),
    }
    return {
        prompt_name: load_prompt(prompt_file)
        for prompt_name, prompt_file in prompt_files.items()
    }


def load_config(path: Path | None = None) -> dict[str, Any]:
    """Load application configuration from ``config.yaml``."""

    config_path = path or CONFIG_PATH

    if not config_path.exists():
        logger.error("LLM configuration file was not found: %s", config_path)
        raise ProviderConfigurationError(f"Configuration file not found: {config_path}")

    try:
        with config_path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
    except yaml.YAMLError as exc:
        logger.error(
            "Failed to parse LLM configuration from %s",
            config_path,
            exc_info=True,
        )
        raise ProviderConfigurationError(
            f"Invalid YAML configuration in {config_path}"
        ) from exc

    if not isinstance(data, dict):
        logger.error("LLM configuration root was not a mapping in %s", config_path)
        raise ProviderConfigurationError(
            f"Configuration root must be a mapping in {config_path}"
        )

    logger.info("Loaded application configuration from %s", config_path)
    return data


def load_llm_config(path: Path | None = None) -> dict[str, Any]:
    """Load the LLM-specific configuration section."""

    data = load_config(path)
    llm_config = data.get("llm_provider")

    if not isinstance(llm_config, dict):
        logger.error("Missing or invalid llm_provider section in config.yaml")
        raise ProviderConfigurationError(
            "Missing or invalid llm_provider section in config.yaml"
        )

    logger.info("Loaded llm_provider configuration")
    return llm_config


def validate_interpreted_action(payload: dict[str, Any]) -> InterpretedAction:
    """Validate raw provider output as an interpreted action."""

    try:
        return InterpretedAction.model_validate(payload)
    except ValidationError as exc:
        logger.warning(
            "Provider output did not validate as interpreted action: %s",
            payload,
            exc_info=True,
        )
        raise ProviderOutputValidationError(
            "Invalid interpreted action payload"
        ) from exc


def validate_narration(payload: dict[str, Any]) -> NarratorResponse:
    """Validate raw provider output as a narration payload."""

    normalized_payload = payload
    if isinstance(payload, dict):
        normalized_payload = dict(payload)

        if isinstance(normalized_payload.get("key_points"), list):
            key_points = normalized_payload["key_points"]
            if len(key_points) > 5:
                logger.warning(
                    "Narration payload contained too many key_points; trimming from %s to 5",
                    len(key_points),
                )
                normalized_payload["key_points"] = key_points[:5]

        if isinstance(normalized_payload.get("injects"), list):
            injects = normalized_payload["injects"]
            if len(injects) > 2:
                logger.warning(
                    "Narration payload contained too many injects; trimming from %s to 2",
                    len(injects),
                )
                normalized_payload["injects"] = injects[:2]

    try:
        return NarratorResponse.model_validate(normalized_payload)
    except ValidationError as exc:
        logger.warning(
            "Provider output did not validate as narration payload: %s",
            normalized_payload,
            exc_info=True,
        )
        raise ProviderOutputValidationError("Invalid narration payload") from exc


def validate_debrief(payload: dict[str, Any]) -> DebriefResponse:
    """Validate raw provider output as a debrief payload."""

    try:
        return DebriefResponse.model_validate(payload)
    except ValidationError as exc:
        logger.warning(
            "Provider output did not validate as debrief payload: %s",
            payload,
            exc_info=True,
        )
        raise ProviderOutputValidationError("Invalid debrief payload") from exc


def validate_scenario(payload: dict[str, Any]) -> Scenario:
    """Validate raw provider output as a scenario payload."""

    normalized_payload = payload
    if isinstance(payload, dict):
        normalized_payload = normalize_scenario_payload(payload)

    try:
        return Scenario.model_validate(normalized_payload)
    except ValidationError as exc:
        logger.warning(
            "Provider output did not validate as scenario payload: %s",
            normalized_payload,
            exc_info=True,
        )
        raise ProviderOutputValidationError("Invalid scenario payload") from exc


def get_llm_provider() -> LLMProvider:
    """Create the configured runtime provider instance."""

    llm_config = load_llm_config()
    provider_name = str(llm_config.get("provider") or "ollama").lower()

    if provider_name == "ollama":
        from src.services.providers.ollama_provider import OllamaProvider

        provider_config = llm_config.get("ollama")
        if not isinstance(provider_config, dict):
            logger.error(
                "Missing or invalid llm_provider.ollama section in config.yaml"
            )
            raise ProviderConfigurationError(
                "Missing or invalid llm_provider.ollama section in config.yaml"
            )
        logger.info("Selected LLM provider=ollama")
        return OllamaProvider(provider_config)

    if provider_name == "openai":
        from src.services.providers.openai_provider import OpenAIProvider

        provider_config = llm_config.get("openai")
        if provider_config is not None and not isinstance(provider_config, dict):
            logger.error("Invalid llm_provider.openai section in config.yaml")
            raise ProviderConfigurationError(
                "Invalid llm_provider.openai section in config.yaml"
            )
        logger.info("Selected LLM provider=openai")
        return OpenAIProvider(provider_config)

    logger.error("Unsupported LLM provider requested: %s", provider_name)
    raise ProviderConfigurationError(f"Unsupported LLM provider: {provider_name}")


from src.services.providers.ollama_provider import OllamaProvider
from src.services.providers.openai_provider import OpenAIProvider

__all__ = [
    "CONFIG_PATH",
    "PROMPTS_DIR",
    "LLMProvider",
    "LLMProviderError",
    "OllamaProvider",
    "OpenAIProvider",
    "ProviderConfigurationError",
    "ProviderOutputValidationError",
    "ProviderResponseFormatError",
    "ProviderUpstreamError",
    "get_llm_provider",
    "load_config",
    "load_llm_config",
    "load_prompt",
    "load_prompt_bundle",
    "validate_debrief",
    "validate_interpreted_action",
    "validate_narration",
    "validate_scenario",
]
