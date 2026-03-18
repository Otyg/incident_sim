from pathlib import Path

import pytest

from src.models.session import SessionFlags, SessionMetrics, SessionState
from src.services.llm_provider import (
    OllamaProvider,
    OpenAIProvider,
    ProviderConfigurationError,
    ProviderOutputValidationError,
    ProviderResponseFormatError,
    ProviderUpstreamError,
    get_llm_provider,
    load_llm_config,
    validate_interpreted_action,
)
from tests.mock_llm_provider import MockLLMProvider


def make_state() -> SessionState:
    return SessionState(
        session_id="sess-1",
        scenario_id="scenario-001",
        scenario_version="1.0",
        audience="krisledning",
        current_time="08:15",
        turn_number=1,
        phase="initial-detection",
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


def write_config(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def test_mock_llm_provider_returns_validated_structures():
    provider = MockLLMProvider()

    interpreted = validate_interpreted_action(
        provider.interpret_action(
            "Vi stänger extern VPN och samlar incidentledningsgruppen."
        )
    )
    narration = provider.generate_narration(make_state())

    assert interpreted.priority == "high"
    assert interpreted.action_types
    assert narration["key_points"]


def test_get_llm_provider_defaults_to_ollama(monkeypatch):
    monkeypatch.setattr(
        "src.services.llm_provider.CONFIG_PATH", Path("/tmp/test-config-default.yaml")
    )
    write_config(
        Path("/tmp/test-config-default.yaml"),
        (
            "llm_provider:\n"
            "  provider: ollama\n"
            "  ollama:\n"
            "    host: http://localhost:11434\n"
            "    model: llama3.2\n"
            "    api_key: null\n"
        ),
    )
    monkeypatch.setattr(
        OllamaProvider, "_create_client", staticmethod(lambda host, headers: object())
    )

    provider = get_llm_provider()

    assert isinstance(provider, OllamaProvider)


def test_get_llm_provider_can_select_openai_stub(monkeypatch):
    monkeypatch.setattr(
        "src.services.llm_provider.CONFIG_PATH", Path("/tmp/test-config-openai.yaml")
    )
    write_config(
        Path("/tmp/test-config-openai.yaml"),
        (
            "llm_provider:\n"
            "  provider: openai\n"
            "  ollama:\n"
            "    host: http://localhost:11434\n"
            "    model: llama3.2\n"
            "  openai:\n"
            "    api_key: null\n"
            "    base_url: null\n"
            "    model: gpt-4.1\n"
        ),
    )

    provider = get_llm_provider()

    assert isinstance(provider, OpenAIProvider)


def test_validate_interpreted_action_raises_for_invalid_provider_output():
    with pytest.raises(ProviderOutputValidationError):
        validate_interpreted_action({"action_summary": "x"})


def test_get_llm_provider_rejects_unknown_provider(monkeypatch):
    monkeypatch.setattr(
        "src.services.llm_provider.CONFIG_PATH", Path("/tmp/test-config-unknown.yaml")
    )
    write_config(
        Path("/tmp/test-config-unknown.yaml"),
        (
            "llm_provider:\n"
            "  provider: unknown\n"
            "  ollama:\n"
            "    host: http://localhost:11434\n"
            "    model: llama3.2\n"
        ),
    )

    with pytest.raises(ProviderConfigurationError):
        get_llm_provider()


def test_ollama_provider_uses_local_host_by_default(monkeypatch):
    captured = {}

    def fake_create_client(host, headers):
        captured["host"] = host
        captured["headers"] = headers
        return object()

    monkeypatch.setattr(
        OllamaProvider, "_create_client", staticmethod(fake_create_client)
    )

    provider = OllamaProvider({"model": "llama3.2"})

    assert provider.host == "http://localhost:11434"
    assert captured == {"host": "http://localhost:11434", "headers": None}


def test_ollama_provider_supports_cloud_host_and_api_key(monkeypatch):
    captured = {}

    def fake_create_client(host, headers):
        captured["host"] = host
        captured["headers"] = headers
        return object()

    monkeypatch.setattr(
        OllamaProvider, "_create_client", staticmethod(fake_create_client)
    )

    provider = OllamaProvider(
        {
            "host": "https://ollama.com",
            "model": "llama3.2",
            "api_key": "secret-token",
        }
    )

    assert provider.host == "https://ollama.com"
    assert captured["headers"] == {"Authorization": "Bearer secret-token"}


def test_ollama_provider_interpret_action_parses_json_response(monkeypatch):
    class FakeClient:
        def chat(self, *, model, messages):
            return {
                "message": {
                    "content": (
                        '{"action_summary":"Samlad tolkning","action_types":["coordination"],'
                        '"targets":["incident_management_team"],"intent":"Skapa samordning",'
                        '"expected_effects":["Battre samordning"],"risks":["Langsammare beslut"],'
                        '"uncertainties":["Resurslage"],"priority":"medium","confidence":0.6}'
                    )
                }
            }

    monkeypatch.setattr(
        OllamaProvider,
        "_create_client",
        staticmethod(lambda host, headers: FakeClient()),
    )

    payload = OllamaProvider({"model": "llama3.2"}).interpret_action(
        "Vi samlar teamet."
    )

    assert payload["action_types"] == ["coordination"]
    assert payload["priority"] == "medium"


def test_ollama_provider_raises_for_non_json_content(monkeypatch):
    class FakeClient:
        def chat(self, *, model, messages):
            return {"message": {"content": "inte json"}}

    monkeypatch.setattr(
        OllamaProvider,
        "_create_client",
        staticmethod(lambda host, headers: FakeClient()),
    )

    with pytest.raises(ProviderResponseFormatError):
        OllamaProvider({"model": "llama3.2"}).interpret_action("Vi samlar teamet.")


def test_ollama_provider_marks_500_errors_as_retryable(monkeypatch):
    class FakeUpstreamError(Exception):
        def __init__(self, message: str, status_code: int) -> None:
            super().__init__(message)
            self.status_code = status_code

    class FakeClient:
        def chat(self, *, model, messages):
            raise FakeUpstreamError("internal error", 500)

    monkeypatch.setattr(
        OllamaProvider,
        "_create_client",
        staticmethod(lambda host, headers: FakeClient()),
    )

    with pytest.raises(ProviderUpstreamError) as exc_info:
        OllamaProvider({"model": "llama3.2"}).interpret_action("Vi samlar teamet.")

    assert exc_info.value.retryable is True
    assert exc_info.value.upstream_status_code == 500
    assert exc_info.value.provider_stage == "interpret_action"


def test_ollama_provider_marks_404_errors_as_non_retryable(monkeypatch):
    class FakeUpstreamError(Exception):
        def __init__(self, message: str, status_code: int) -> None:
            super().__init__(message)
            self.status_code = status_code

    class FakeClient:
        def chat(self, *, model, messages):
            raise FakeUpstreamError("not found", 404)

    monkeypatch.setattr(
        OllamaProvider,
        "_create_client",
        staticmethod(lambda host, headers: FakeClient()),
    )

    with pytest.raises(ProviderUpstreamError) as exc_info:
        OllamaProvider({"model": "llama3.2"}).generate_narration(make_state())

    assert exc_info.value.retryable is False
    assert exc_info.value.upstream_status_code == 404
    assert exc_info.value.provider_stage == "generate_narration"


def test_load_llm_config_reads_provider_section(monkeypatch):
    monkeypatch.setattr(
        "src.services.llm_provider.CONFIG_PATH", Path("/tmp/test-config-load.yaml")
    )
    write_config(
        Path("/tmp/test-config-load.yaml"),
        (
            "llm_provider:\n"
            "  provider: ollama\n"
            "  ollama:\n"
            "    host: http://localhost:11434\n"
            "    model: llama3.2\n"
        ),
    )

    llm_config = load_llm_config()

    assert llm_config["provider"] == "ollama"
    assert llm_config["ollama"]["model"] == "llama3.2"
