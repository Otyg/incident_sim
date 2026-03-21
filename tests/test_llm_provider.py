from pathlib import Path

import pytest

from src.models.session import SessionFlags, SessionMetrics, SessionState
from src.services.llm_provider import (
    OllamaProvider,
    OpenAIProvider,
    OpenRouterProvider,
    ProviderConfigurationError,
    ProviderOutputValidationError,
    ProviderResponseFormatError,
    ProviderUpstreamError,
    get_llm_provider,
    validate_debrief,
    load_llm_config,
    validate_interpreted_action,
    validate_narration,
    validate_scenario,
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
    scenario = validate_scenario(
        {
            **provider.generate_scenario_draft("# Scenario", "markdown"),
            "original_text": "# Scenario",
        }
    )

    assert interpreted.priority == "high"
    assert interpreted.action_types
    assert narration["key_points"]
    assert scenario.original_text == "# Scenario"


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


def test_get_llm_provider_can_select_openrouter(monkeypatch):
    monkeypatch.setattr(
        "src.services.llm_provider.CONFIG_PATH",
        Path("/tmp/test-config-openrouter.yaml"),
    )
    write_config(
        Path("/tmp/test-config-openrouter.yaml"),
        (
            "llm_provider:\n"
            "  provider: openrouter\n"
            "  openrouter:\n"
            "    api_key: secret-token\n"
            "    base_url: https://openrouter.ai/api/v1\n"
            "    model: openai/gpt-4.1-mini\n"
        ),
    )

    provider = get_llm_provider()

    assert isinstance(provider, OpenRouterProvider)


def test_validate_interpreted_action_raises_for_invalid_provider_output():
    with pytest.raises(ProviderOutputValidationError):
        validate_interpreted_action({"action_summary": "x"})


def test_validate_narration_trims_extra_key_points_and_injects():
    response = validate_narration(
        {
            "situation_update": "Laget utvecklas snabbt och underlaget ar tillrackligt for narrationsvalidering.",
            "key_points": ["A", "B", "C", "D", "E", "F"],
            "new_consequences": [],
            "injects": [
                {"type": "media", "title": "I1", "message": "Inject ett."},
                {"type": "operations", "title": "I2", "message": "Inject tva."},
                {"type": "executive", "title": "I3", "message": "Inject tre."},
            ],
            "decisions_to_consider": ["Vad ar viktigast nu?"],
            "facilitator_notes": "Trimning ska gora payloaden fortsatt anvandbar.",
        }
    )

    assert response.key_points == ["A", "B", "C", "D", "E"]
    assert len(response.injects) == 2


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
        def chat(self, *, model, messages, format, stream):
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


def test_ollama_provider_generate_scenario_draft_parses_json_response(monkeypatch):
    class FakeClient:
        def chat(self, *, model, messages, format, stream):
            return {
                "message": {
                    "content": (
                        '{"id":"scenario-draft-001","title":"Scenarioutkast","version":"1.0",'
                        '"description":"Kort sammanfattning av utkastet.","audiences":["krisledning"],'
                        '"training_goals":["Öva lägesuppfattning"],"difficulty":"medium","timebox_minutes":60,'
                        '"background":{"organization_type":"kommun","context":"Testkontext för utkast.",'
                        '"threat_actor":"okänd angripare","assumptions":[]},'
                        '"states":[{"id":"state-initial-detection","phase":"initial-detection",'
                        '"title":"Initial detektion","description":"Första läget.","time":"08:15",'
                        '"impact_level":2,"narration":{"default":{"situation_update":"Det här är ett tillräckligt långt startnarrativ för att validera scenarioutkastet.",'
                        '"key_points":["A","B"],"new_consequences":[],"injects":[],"decisions_to_consider":["Vad nu?"],"facilitator_notes":"Notering."}}}],'
                        '"actors":[],"inject_catalog":[],"text_matchers":[],"target_aliases":[],"interpretation_hints":[],'
                        '"rules":[],"executable_rules":[],"presentation_guidelines":{"krisledning":{"focus":["beslut"],"tone":"strategisk"}}}'
                    )
                }
            }

    monkeypatch.setattr(
        OllamaProvider,
        "_create_client",
        staticmethod(lambda host, headers: FakeClient()),
    )

    payload = OllamaProvider({"model": "llama3.2"}).generate_scenario_draft(
        "# Scenario", "markdown"
    )

    assert payload["id"] == "scenario-draft-001"
    assert payload["states"][0]["phase"] == "initial-detection"


def test_ollama_provider_extracts_json_from_thinking_when_content_is_missing(
    monkeypatch,
):
    class FakeClient:
        def chat(self, *, model, messages, format, stream):
            return {
                "message": {
                    "content": None,
                    "thinking": (
                        '{"action_summary":"Samlad tolkning","action_types":["coordination"],'
                        '"targets":["incident_management_team"],"intent":"Skapa samordning",'
                        '"expected_effects":["Battre samordning"],"risks":["Langsammare beslut"],'
                        '"uncertainties":["Resurslage"],"priority":"medium","confidence":0.6}'
                    ),
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

    assert payload["priority"] == "medium"


def test_ollama_provider_passes_json_format_to_client(monkeypatch):
    captured = {}

    class FakeClient:
        def chat(self, *, model, messages, format, stream):
            captured["format"] = format
            captured["stream"] = stream
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

    OllamaProvider({"model": "llama3.2"}).interpret_action("Vi samlar teamet.")

    assert captured["format"] == "json"
    assert captured["stream"] is False


def test_openrouter_provider_builds_expected_headers():
    provider = OpenRouterProvider(
        {
            "api_key": "secret-token",
            "app_url": "https://example.com",
            "app_name": "Incident Exercise Support",
            "model": "openai/gpt-4.1-mini",
        }
    )

    headers = provider._build_headers()

    assert headers["Authorization"] == "Bearer secret-token"
    assert headers["HTTP-Referer"] == "https://example.com"
    assert headers["X-Title"] == "Incident Exercise Support"


def test_openrouter_provider_requires_api_key():
    provider = OpenRouterProvider({"model": "openai/gpt-4.1-mini"})

    with pytest.raises(ProviderConfigurationError):
        provider._build_headers()


def test_openrouter_provider_interpret_action_parses_json_response(monkeypatch):
    def fake_post_json(self, payload):
        assert payload["model"] == "openai/gpt-4.1-mini"
        assert payload["response_format"] == {"type": "json_object"}
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"action_summary":"Samlad tolkning","action_types":["coordination"],'
                            '"targets":["incident_management_team"],"intent":"Skapa samordning",'
                            '"expected_effects":["Battre samordning"],"risks":["Langsammare beslut"],'
                            '"uncertainties":["Resurslage"],"priority":"medium","confidence":0.6}'
                        )
                    }
                }
            ]
        }

    monkeypatch.setattr(OpenRouterProvider, "_post_json", fake_post_json)

    payload = OpenRouterProvider(
        {
            "api_key": "secret-token",
            "model": "openai/gpt-4.1-mini",
        }
    ).interpret_action("Vi samlar teamet.")

    assert payload["action_types"] == ["coordination"]
    assert payload["priority"] == "medium"


def test_openrouter_provider_raises_retryable_upstream_error_on_429(monkeypatch):
    class FakeHttpError(Exception):
        code = 429

    def fake_post_json(self, payload):
        raise FakeHttpError("rate limited")

    monkeypatch.setattr(OpenRouterProvider, "_post_json", fake_post_json)

    provider = OpenRouterProvider(
        {
            "api_key": "secret-token",
            "model": "openai/gpt-4.1-mini",
        }
    )

    with pytest.raises(ProviderUpstreamError) as exc_info:
        provider.interpret_action("Vi samlar teamet.")

    assert exc_info.value.upstream_status_code == 429
    assert exc_info.value.retryable is True


def test_validate_scenario_downgrades_incomplete_executable_rules():
    provider = MockLLMProvider()
    payload = provider.generate_scenario_draft("# Scenario", "markdown")
    payload["original_text"] = "# Scenario"
    payload["executable_rules"] = [
        {
            "id": "webbhosting-driftregel-1",
            "name": "Rollback dröjer av prestigeskäl",
            "conditions": ["Rollback försenas"],
            "effects": ["Kommunikation dröjer"],
        }
    ]

    scenario = validate_scenario(payload)

    assert scenario.executable_rules == []
    assert scenario.rules[0].id == "webbhosting-driftregel-1"
    assert scenario.rules[0].name == "Rollback dröjer av prestigeskäl"


def test_validate_scenario_normalizes_duplicate_phases_and_special_characters():
    provider = MockLLMProvider()
    payload = provider.generate_scenario_draft("# Scenario", "markdown")
    payload["id"] = "Webbhosting / Drift?!"
    payload["original_text"] = "# Scenario"
    payload["states"] = [
        {
            **payload["states"][0],
            "id": "State: Initial / Detektion",
            "phase": "Initial Detektion!!!",
            "title": "Initial Detektion",
        },
        {
            **payload["states"][1],
            "id": "State: Initial / Detektion",
            "phase": "Initial Detektion!!!",
            "title": "Initial Detektion",
        },
    ]

    scenario = validate_scenario(payload)

    assert scenario.id == "webbhosting-drift"
    assert scenario.states[0].id == "state-initial-detektion"
    assert scenario.states[0].phase == "initial-detektion"
    assert scenario.states[1].phase == "initial-detektion-2"


def test_validate_scenario_drops_invalid_set_flag_effects():
    provider = MockLLMProvider()
    payload = provider.generate_scenario_draft("# Scenario", "markdown")
    payload["original_text"] = "# Scenario"
    payload["executable_rules"] = [
        {
            "id": "rule-declare-incident",
            "name": "Försök sätta incidentflagga",
            "trigger": "turn_processed",
            "effects": [
                {
                    "type": "set_flag",
                    "value": "incident_declared",
                }
            ],
        }
    ]

    scenario = validate_scenario(payload)

    assert scenario.executable_rules == []
    assert scenario.rules[0].id == "rule-declare-incident"


def test_validate_scenario_maps_inject_effect_value_to_inject_id():
    provider = MockLLMProvider()
    payload = provider.generate_scenario_draft("# Scenario", "markdown")
    payload["original_text"] = "# Scenario"
    payload["executable_rules"] = [
        {
            "id": "rule-trigger-inject",
            "name": "Aktivera inject",
            "trigger": "turn_processed",
            "effects": [
                {
                    "type": "add_active_inject",
                    "value": "inject-executive-001",
                }
            ],
        }
    ]

    scenario = validate_scenario(payload)

    assert len(scenario.executable_rules) == 1
    assert scenario.executable_rules[0].effects[0].inject_id == "inject-executive-001"


def test_validate_scenario_drops_unsupported_condition_facts():
    provider = MockLLMProvider()
    payload = provider.generate_scenario_draft("# Scenario", "markdown")
    payload["original_text"] = "# Scenario"
    payload["executable_rules"] = [
        {
            "id": "rule-rollback-condition",
            "name": "Ogiltig rollback-flagga",
            "trigger": "turn_processed",
            "conditions": [
                {
                    "fact": "state.flags.rollback_initiated",
                    "operator": "equals",
                    "value": True,
                }
            ],
            "effects": [
                {
                    "type": "append_consequence",
                    "item": "Rollback har påbörjats.",
                }
            ],
        }
    ]

    scenario = validate_scenario(payload)

    assert len(scenario.executable_rules) == 1
    assert scenario.executable_rules[0].conditions == []
    assert scenario.executable_rules[0].effects[0].type == "append_consequence"


def test_validate_scenario_fills_missing_initial_state_runtime_fields():
    provider = MockLLMProvider()
    payload = provider.generate_scenario_draft(
        "# Scenario\n\nKlockan är 09:12.", "markdown"
    )
    payload["original_text"] = "# Scenario\n\nKlockan är 09:12."
    payload["states"][0].pop("time", None)
    payload["states"][0].pop("impact_level", None)
    payload["states"][0].pop("narration", None)

    scenario = validate_scenario(payload)

    assert scenario.states[0].time == "09:12"
    assert scenario.states[0].impact_level == 3
    assert scenario.states[0].narration is not None


def test_validate_scenario_converts_string_state_narration_to_object():
    provider = MockLLMProvider()
    payload = provider.generate_scenario_draft("# Scenario", "markdown")
    payload["original_text"] = "# Scenario"
    payload["states"][1]["narration"] = (
        "Fler kunder rapporterar problem. Övervakningen visar flera HTTP-checkar går röda."
    )

    scenario = validate_scenario(payload)

    assert scenario.states[1].narration is not None
    assert (
        scenario.states[1].narration.default.situation_update
        == "Fler kunder rapporterar problem. Övervakningen visar flera HTTP-checkar går röda."
    )


def test_ollama_provider_raises_for_non_json_content(monkeypatch):
    class FakeClient:
        def chat(self, *, model, messages, format, stream):
            return {"message": {"content": "inte json"}}

    monkeypatch.setattr(
        OllamaProvider,
        "_create_client",
        staticmethod(lambda host, headers: FakeClient()),
    )

    with pytest.raises(ProviderResponseFormatError):
        OllamaProvider({"model": "llama3.2"}).interpret_action("Vi samlar teamet.")


def test_ollama_provider_response_format_error_includes_stage_and_excerpt(monkeypatch):
    class FakeClient:
        def chat(self, *, model, messages, format, stream):
            return {"message": {"content": '{"broken": true "oops"}'}}

    monkeypatch.setattr(
        OllamaProvider,
        "_create_client",
        staticmethod(lambda host, headers: FakeClient()),
    )

    with pytest.raises(ProviderResponseFormatError) as exc_info:
        OllamaProvider({"model": "llama3.2"}).generate_narration(make_state())

    assert exc_info.value.provider_stage == "generate_narration"
    assert exc_info.value.retryable is True
    assert '"oops"' in (exc_info.value.raw_response_excerpt or "")


def test_ollama_provider_repairs_trailing_comma_json(monkeypatch):
    class FakeClient:
        def chat(self, *, model, messages, format, stream):
            return {
                "message": {
                    "content": (
                        '{"action_summary":"Samlad tolkning","action_types":["coordination"],'
                        '"targets":["incident_management_team"],"intent":"Skapa samordning",'
                        '"expected_effects":["Battre samordning"],"risks":["Langsammare beslut"],'
                        '"uncertainties":["Resurslage"],"priority":"medium","confidence":0.6,}'
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

    assert payload["priority"] == "medium"


def test_ollama_provider_repairs_fenced_json(monkeypatch):
    class FakeClient:
        def chat(self, *, model, messages, format, stream):
            return {
                "message": {
                    "content": (
                        "```json\n"
                        '{"action_summary":"Samlad tolkning","action_types":["coordination"],'
                        '"targets":["incident_management_team"],"intent":"Skapa samordning",'
                        '"expected_effects":["Battre samordning"],"risks":["Langsammare beslut"],'
                        '"uncertainties":["Resurslage"],"priority":"medium","confidence":0.6}'
                        "\n```"
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


def test_ollama_provider_marks_500_errors_as_retryable(monkeypatch):
    class FakeUpstreamError(Exception):
        def __init__(self, message: str, status_code: int) -> None:
            super().__init__(message)
            self.status_code = status_code

    class FakeClient:
        def chat(self, *, model, messages, format, stream):
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
        def chat(self, *, model, messages, format, stream):
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


def test_ollama_provider_appends_scenario_prompt_instructions_to_narration(
    monkeypatch,
):
    captured = {}

    class FakeClient:
        def chat(self, *, model, messages, format, stream):
            captured["system_prompt"] = messages[0]["content"]
            return {
                "message": {
                    "content": (
                        '{"situation_update":"Tillrackligt lang narrationsuppdatering for validering i testfallet.",'
                        '"key_points":["A","B"],"new_consequences":[],"injects":[],'
                        '"decisions_to_consider":[],"facilitator_notes":"Notering."}'
                    )
                }
            }

    monkeypatch.setattr(
        OllamaProvider,
        "_create_client",
        staticmethod(lambda host, headers: FakeClient()),
    )

    scenario_payload = MockLLMProvider().generate_scenario_draft("# Scenario", "markdown")
    scenario_payload["original_text"] = "# Scenario"
    scenario_payload["prompt_instructions"] = {
        "default": {"items": ["Namnge alltid påverkad miljö i situation_update."]},
        "by_audience": {
            "krisledning": {"items": ["Lyft beslutsbehov för ledningsnivån."]}
        },
    }
    scenario = validate_scenario(scenario_payload)

    payload = OllamaProvider({"model": "llama3.2"}).generate_narration(
        make_state(),
        scenario=scenario,
    )

    assert payload["key_points"] == ["A", "B"]
    assert "Scenario-specific instructions:" in captured["system_prompt"]
    assert "Namnge alltid påverkad miljö i situation_update." in captured[
        "system_prompt"
    ]
    assert "Lyft beslutsbehov för ledningsnivån." in captured["system_prompt"]
    assert "Return only a single JSON object" in captured["system_prompt"]


def test_openrouter_provider_appends_scenario_prompt_instructions_to_debrief(
    monkeypatch,
):
    captured = {}

    def fake_post_json(self, payload):
        captured["system_prompt"] = payload["messages"][0]["content"]
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"exercise_summary":"Sammanfattning av ovningen.",'
                            '"timeline_summary":[{"turn_number":1,"summary":"Steg 1","outcome":"Utfall 1"}],'
                            '"strengths":["Styrka 1","Styrka 2"],'
                            '"development_areas":["Omrade 1","Omrade 2"],'
                            '"debrief_questions":["Fraga 1","Fraga 2","Fraga 3"],'
                            '"recommended_follow_ups":["Uppfoljning 1"],'
                            '"facilitator_notes":"Notering."}'
                        )
                    }
                }
            ]
        }

    monkeypatch.setattr(OpenRouterProvider, "_post_json", fake_post_json)

    scenario_payload = MockLLMProvider().generate_scenario_draft("# Scenario", "markdown")
    scenario_payload["original_text"] = "# Scenario"
    scenario_payload["prompt_instructions"] = {
        "default": {"text": "Beskriv miljokontext explicit i summeringen."},
        "by_audience": {
            "krisledning": {"items": ["Betona riskacceptans och mandatfrågor."]}
        },
    }
    scenario = validate_scenario(scenario_payload)
    debrief = validate_debrief(
        OpenRouterProvider(
            {"api_key": "secret-token", "model": "openai/gpt-4.1-mini"}
        ).generate_debrief(scenario, make_state(), [])
    )

    assert debrief.strengths == ["Styrka 1", "Styrka 2"]
    assert "Beskriv miljokontext explicit i summeringen." in captured["system_prompt"]
    assert "Betona riskacceptans och mandatfrågor." in captured["system_prompt"]
    assert "Expected shape:" in captured["system_prompt"]


def test_ollama_provider_does_not_append_scenario_prompt_instructions_to_interpret_action(
    monkeypatch,
):
    captured = {}

    class FakeClient:
        def chat(self, *, model, messages, format, stream):
            captured["system_prompt"] = messages[0]["content"]
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

    assert payload["priority"] == "medium"
    assert "Scenario-specific instructions:" not in captured["system_prompt"]
