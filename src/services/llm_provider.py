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
    pass


class ProviderOutputValidationError(LLMProviderError):
    pass


class ProviderConfigurationError(LLMProviderError):
    pass


class LLMProvider(ABC):
    @abstractmethod
    def interpret_action(self, participant_input: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def generate_narration(self, state: SessionState) -> dict[str, Any]:
        raise NotImplementedError


def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding='utf-8').strip()


def validate_interpreted_action(payload: dict[str, Any]) -> InterpretedAction:
    try:
        return InterpretedAction.model_validate(payload)
    except ValidationError as exc:
        raise ProviderOutputValidationError('Invalid interpreted action payload') from exc


def validate_narration(payload: dict[str, Any]) -> NarratorResponse:
    try:
        return NarratorResponse.model_validate(payload)
    except ValidationError as exc:
        raise ProviderOutputValidationError('Invalid narration payload') from exc


class OpenAIProvider(LLMProvider):
    def __init__(self) -> None:
        self.interpret_prompt = load_prompt('interpret_action.txt')
        self.narration_prompt = load_prompt('generate_narration.txt')

    def interpret_action(self, participant_input: str) -> dict[str, Any]:
        raise ProviderConfigurationError('OpenAIProvider is not implemented yet')

    def generate_narration(self, state: SessionState) -> dict[str, Any]:
        raise ProviderConfigurationError('OpenAIProvider is not implemented yet')


def get_llm_provider() -> LLMProvider:
    provider_name = os.getenv('INCIDENT_SIM_LLM_PROVIDER', 'openai').lower()

    if provider_name == 'openai':
        return OpenAIProvider()

    raise ProviderConfigurationError(f'Unsupported LLM provider: {provider_name}')
