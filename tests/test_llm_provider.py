import pytest

from src.models.session import SessionFlags, SessionMetrics, SessionState
from src.services.llm_provider import (
    OpenAIProvider,
    ProviderConfigurationError,
    ProviderOutputValidationError,
    get_llm_provider,
    validate_interpreted_action,
)
from tests.mock_llm_provider import MockLLMProvider


def make_state() -> SessionState:
    return SessionState(
        session_id='sess-1',
        scenario_id='scenario-001',
        scenario_version='1.0',
        audience='krisledning',
        current_time='08:15',
        turn_number=1,
        phase='initial-detection',
        metrics=SessionMetrics(
            impact_level=2,
            media_pressure=1,
            service_disruption=1,
            leadership_pressure=0,
            public_confusion=0,
            attack_surface=3,
        ),
        flags=SessionFlags(),
    )


def test_mock_llm_provider_returns_validated_structures():
    provider = MockLLMProvider()

    interpreted = validate_interpreted_action(
        provider.interpret_action('Vi stänger extern VPN och samlar incidentledningsgruppen.')
    )
    narration = provider.generate_narration(make_state())

    assert interpreted.priority == 'high'
    assert interpreted.action_types
    assert narration['key_points']


def test_get_llm_provider_defaults_to_openai_stub(monkeypatch):
    monkeypatch.delenv('INCIDENT_SIM_LLM_PROVIDER', raising=False)

    provider = get_llm_provider()

    assert isinstance(provider, OpenAIProvider)


def test_validate_interpreted_action_raises_for_invalid_provider_output():
    with pytest.raises(ProviderOutputValidationError):
        validate_interpreted_action({'action_summary': 'x'})


def test_get_llm_provider_rejects_unknown_provider(monkeypatch):
    monkeypatch.setenv('INCIDENT_SIM_LLM_PROVIDER', 'unknown')

    with pytest.raises(ProviderConfigurationError):
        get_llm_provider()
