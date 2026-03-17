"""Provider abstractions and schema validation helpers for LLM output.

The module defines the provider interface used by the API layer, a stubbed
OpenAI provider selection mechanism, prompt loading helpers and validation
wrappers that convert raw provider payloads into typed Pydantic models.
"""

import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from src.models.session import SessionState
from src.schemas.interpreted_action import InterpretedAction
from src.schemas.narrator_response import NarratorResponse


PROMPTS_DIR = Path(__file__).resolve().parents[1] / 'prompts'


class LLMProviderError(Exception):
    """Base exception for provider-related failures."""

    pass


class ProviderOutputValidationError(LLMProviderError):
    """Raised when provider output cannot be validated against schemas."""

    pass


class ProviderConfigurationError(LLMProviderError):
    """Raised when provider configuration is unsupported or unavailable."""

    pass


class LLMProvider(ABC):
    """Abstract interface for action interpretation and narration providers."""

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

    return (PROMPTS_DIR / name).read_text(encoding='utf-8').strip()


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
        raise ProviderOutputValidationError('Invalid interpreted action payload') from exc


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
        raise ProviderOutputValidationError('Invalid narration payload') from exc


class OpenAIProvider(LLMProvider):
    """Stub implementation for a future OpenAI-backed provider.

    The class currently loads prompt files but intentionally raises a
    configuration error when called because external integration is not yet
    implemented in this project.
    """

    def __init__(self) -> None:
        self.interpret_prompt = load_prompt('interpret_action.txt')
        self.narration_prompt = load_prompt('generate_narration.txt')

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

        raise ProviderConfigurationError('OpenAIProvider is not implemented yet')

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

        raise ProviderConfigurationError('OpenAIProvider is not implemented yet')


def get_llm_provider() -> LLMProvider:
    """Create the configured runtime provider instance.

    The provider is selected from ``INCIDENT_SIM_LLM_PROVIDER``. Only the
    ``openai`` value is currently supported at runtime, and it maps to a stub
    provider that returns controlled errors until a real integration is added.

    Returns:
        LLMProvider: Configured provider instance.

    Raises:
        ProviderConfigurationError: If the configured provider name is not
            supported.
    """

    provider_name = os.getenv('INCIDENT_SIM_LLM_PROVIDER', 'openai').lower()

    if provider_name == 'openai':
        return OpenAIProvider()

    raise ProviderConfigurationError(f'Unsupported LLM provider: {provider_name}')
