import asyncio
import json


from src import api as api_module
from src.main import app
from src.services.llm_provider import OpenAIProvider, ProviderUpstreamError
from tests.mock_llm_provider import MockLLMProvider


def request_json(method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    messages = []
    payload = json.dumps(body).encode() if body is not None else b""
    delivered = False

    async def receive():
        nonlocal delivered
        if not delivered:
            delivered = True
            return {"type": "http.request", "body": payload, "more_body": False}

        return {"type": "http.disconnect"}

    async def send(message):
        messages.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [(b"content-type", b"application/json")],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "root_path": "",
    }

    asyncio.run(app(scope, receive, send))

    status = messages[0]["status"]
    response_body = messages[1].get("body", b"")
    parsed_body = json.loads(response_body) if response_body else {}
    return status, parsed_body


def sample_scenario_payload():
    return {
        "id": "scenario-001",
        "title": "Ransomware mot kommunal verksamhet",
        "version": "1.0",
        "description": "Testscenario för API-flödet.",
        "audiences": ["krisledning", "it-ledning"],
        "training_goals": ["Öva initial lägesuppfattning"],
        "difficulty": "medium",
        "timebox_minutes": 90,
        "background": {
            "organization_type": "kommun",
            "context": "Testkontext",
            "threat_actor": "okänd angripare",
            "assumptions": [],
        },
        "initial_state": {
            "time": "08:15",
            "phase": "initial-detection",
            "known_facts": ["Inloggningsproblem"],
            "unknowns": ["Omfattning oklar"],
            "affected_systems": ["AD"],
            "business_impact": ["Intern påverkan"],
            "impact_level": 2,
            "initial_narration": {
                "default": {
                    "situation_update": "Läget är fortsatt osäkert och flera verksamheter rapporterar störningar.",
                    "key_points": [
                        "Inloggningsproblem påverkar flera användare.",
                        "Omfattningen är fortfarande oklar.",
                    ],
                    "new_consequences": [],
                    "injects": [],
                    "decisions_to_consider": ["Behöver läget eskaleras direkt?"],
                    "facilitator_notes": "Fördefinierat startnarrativ för testsessionen.",
                }
            },
        },
        "actors": [],
        "inject_catalog": [],
        "rules": [],
        "executable_rules": [],
        "presentation_guidelines": {
            "krisledning": {"focus": ["beslut"], "tone": "strategisk"},
            "it-ledning": {"focus": ["system"], "tone": "operativ"},
        },
    }


def datadriven_scenario_payload():
    payload = sample_scenario_payload()
    payload["executable_rules"] = [
        {
            "id": "rule-session-start",
            "name": "Startregel",
            "trigger": "session_started",
            "effects": [
                {
                    "type": "append_focus_item",
                    "item": "Bekräfta initial lägesbild med verksamheten.",
                },
                {
                    "type": "append_exercise_log",
                    "log_type": "scenario_event",
                    "message": "Sessionen startade i datadrivet läge.",
                },
            ],
            "priority": "high",
            "once": True,
        },
        {
            "id": "rule-phase-change",
            "name": "Containment byter fas",
            "trigger": "turn_processed",
            "conditions": [
                {
                    "fact": "state.flags.external_access_restricted",
                    "operator": "equals",
                    "value": True,
                }
            ],
            "effects": [{"type": "set_phase", "phase": "containment"}],
            "priority": "high",
            "once": True,
        },
    ]
    return payload


def test_get_default_sample_scenario():
    status, body = request_json("GET", "/sample-scenarios/default")

    assert status == 200
    assert body["id"] == "scenario-municipality-ransomware-001"
    assert body["difficulty"] == "high"
    assert "kommunikation" in body["audiences"]
    assert len(body["inject_catalog"]) >= 2


def test_create_and_get_scenario():
    scenario = sample_scenario_payload()

    create_status, create_body = request_json("POST", "/scenarios", scenario)
    get_status, get_body = request_json("GET", "/scenarios/scenario-001")

    assert create_status == 200
    assert create_body["id"] == "scenario-001"
    assert get_status == 200
    assert get_body["title"] == scenario["title"]


def test_list_scenarios_returns_saved_scenarios_in_id_order():
    scenario_b = sample_scenario_payload()
    scenario_b["id"] = "scenario-002"
    scenario_b["title"] = "Scenario B"

    scenario_a = sample_scenario_payload()
    scenario_a["id"] = "scenario-001"
    scenario_a["title"] = "Scenario A"

    request_json("POST", "/scenarios", scenario_b)
    request_json("POST", "/scenarios", scenario_a)

    status, body = request_json("GET", "/scenarios")

    assert status == 200
    assert [item["id"] for item in body] == ["scenario-001", "scenario-002"]
    assert [item["title"] for item in body] == ["Scenario A", "Scenario B"]


def test_create_and_get_session_from_existing_scenario(monkeypatch):
    monkeypatch.setattr(api_module, "get_llm_provider", lambda: MockLLMProvider())
    scenario = sample_scenario_payload()
    request_json("POST", "/scenarios", scenario)

    create_status, create_body = request_json(
        "POST",
        "/sessions",
        {"scenario_id": "scenario-001", "audience": "krisledning"},
    )
    get_status, get_body = request_json(
        "GET", f"/sessions/{create_body['session_state']['session_id']}"
    )

    assert create_status == 200
    assert create_body["session_state"]["scenario_id"] == "scenario-001"
    assert create_body["session_state"]["audience"] == "krisledning"
    assert create_body["initial_narration"]["situation_update"] == (
        "Läget är fortsatt osäkert och flera verksamheter rapporterar störningar."
    )
    assert get_status == 200
    assert get_body["session_id"] == create_body["session_state"]["session_id"]


def test_create_session_prefers_audience_specific_initial_narration(monkeypatch):
    monkeypatch.setattr(api_module, "get_llm_provider", lambda: MockLLMProvider())
    scenario = sample_scenario_payload()
    scenario["initial_state"]["initial_narration"]["by_audience"] = {
        "krisledning": {
            "situation_update": "Krisledningen möter ett snabbt eskalerande läge med tydlig verksamhetspåverkan.",
            "key_points": [
                "Beslutsbehovet är omedelbart.",
                "Samordning mellan funktioner behöver etableras nu.",
            ],
            "new_consequences": [],
            "injects": [],
            "decisions_to_consider": ["Vilket första ledningsbeslut behöver fattas?"],
            "facilitator_notes": "Audience-specifikt startnarrativ för krisledning.",
        }
    }
    request_json("POST", "/scenarios", scenario)

    create_status, create_body = request_json(
        "POST",
        "/sessions",
        {"scenario_id": "scenario-001", "audience": "krisledning"},
    )

    assert create_status == 200
    assert create_body["initial_narration"]["situation_update"] == (
        "Krisledningen möter ett snabbt eskalerande läge med tydlig verksamhetspåverkan."
    )


def test_create_session_falls_back_to_default_initial_narration(monkeypatch):
    monkeypatch.setattr(api_module, "get_llm_provider", lambda: MockLLMProvider())
    scenario = sample_scenario_payload()
    scenario["initial_state"]["initial_narration"]["by_audience"] = {
        "krisledning": {
            "situation_update": "Krisledningens variant.",
            "key_points": [
                "Ledningsnivån behöver snabbt mobiliseras.",
                "Kommunikationsbehovet växer.",
            ],
            "new_consequences": [],
            "injects": [],
            "decisions_to_consider": ["Ska krisledningen sammankallas?"],
            "facilitator_notes": "Audience-specifik variant.",
        }
    }
    request_json("POST", "/scenarios", scenario)

    create_status, create_body = request_json(
        "POST",
        "/sessions",
        {"scenario_id": "scenario-001", "audience": "it-ledning"},
    )

    assert create_status == 200
    assert create_body["initial_narration"]["situation_update"] == (
        "Läget är fortsatt osäkert och flera verksamheter rapporterar störningar."
    )


def test_create_session_does_not_call_provider_generate_narration(monkeypatch):
    class FailingInitialNarrationProvider:
        def generate_narration(self, state) -> dict:
            raise AssertionError(
                "generate_narration should not be called during session creation"
            )

    monkeypatch.setattr(
        api_module,
        "get_llm_provider",
        lambda: FailingInitialNarrationProvider(),
    )
    request_json("POST", "/scenarios", sample_scenario_payload())

    create_status, create_body = request_json(
        "POST",
        "/sessions",
        {"scenario_id": "scenario-001", "audience": "krisledning"},
    )

    assert create_status == 200
    assert create_body["initial_narration"]["key_points"]


def test_post_turn_returns_basic_turn_response(monkeypatch):
    monkeypatch.setattr(api_module, "get_llm_provider", lambda: MockLLMProvider())

    scenario = sample_scenario_payload()
    request_json("POST", "/scenarios", scenario)
    _, session = request_json(
        "POST",
        "/sessions",
        {"scenario_id": "scenario-001", "audience": "krisledning"},
    )

    status, body = request_json(
        "POST",
        f"/sessions/{session['session_state']['session_id']}/turns",
        {
            "participant_input": "Vi stänger extern VPN och samlar incidentledningsgruppen."
        },
    )

    assert status == 200
    assert body["turn_number"] == 1
    assert body["participant_input"].startswith("Vi stänger extern VPN")
    assert body["interpreted_action"]["priority"] == "high"
    assert body["state_snapshot"]["current_time"] == "08:30"
    assert (
        body["state_snapshot"]["session_id"] == session["session_state"]["session_id"]
    )
    assert body["narrator_response"]["key_points"]


def test_post_turn_applies_datadriven_phase_change(monkeypatch):
    monkeypatch.setattr(api_module, "get_llm_provider", lambda: MockLLMProvider())
    request_json("POST", "/scenarios", datadriven_scenario_payload())
    _, session = request_json(
        "POST",
        "/sessions",
        {"scenario_id": "scenario-001", "audience": "krisledning"},
    )

    status, body = request_json(
        "POST",
        f"/sessions/{session['session_state']['session_id']}/turns",
        {"participant_input": "Vi stänger extern VPN."},
    )

    assert status == 200
    assert body["state_snapshot"]["phase"] == "containment"


def test_manual_phase_change_updates_session_when_phase_is_defined(monkeypatch):
    monkeypatch.setattr(api_module, "get_llm_provider", lambda: MockLLMProvider())
    request_json("POST", "/scenarios", datadriven_scenario_payload())
    _, session = request_json(
        "POST",
        "/sessions",
        {"scenario_id": "scenario-001", "audience": "krisledning"},
    )

    status, body = request_json(
        "POST",
        f"/sessions/{session['session_state']['session_id']}/phase",
        {"phase": "containment"},
    )

    assert status == 200
    assert body["phase"] == "containment"
    assert any(
        item["text"] == "Manuellt fasbyte: initial-detection -> containment"
        for item in body["exercise_log"]
    )


def test_manual_phase_change_rejects_undefined_phase(monkeypatch):
    monkeypatch.setattr(api_module, "get_llm_provider", lambda: MockLLMProvider())
    request_json("POST", "/scenarios", datadriven_scenario_payload())
    _, session = request_json(
        "POST",
        "/sessions",
        {"scenario_id": "scenario-001", "audience": "krisledning"},
    )

    status, body = request_json(
        "POST",
        f"/sessions/{session['session_state']['session_id']}/phase",
        {"phase": "recovery"},
    )

    assert status == 400
    assert body["detail"] == "Phase is not defined in the scenario"


def test_post_turn_returns_503_for_unavailable_openai_provider(monkeypatch):
    scenario = sample_scenario_payload()
    request_json("POST", "/scenarios", scenario)
    monkeypatch.setattr(api_module, "get_llm_provider", lambda: MockLLMProvider())
    _, session = request_json(
        "POST",
        "/sessions",
        {"scenario_id": "scenario-001", "audience": "krisledning"},
    )
    monkeypatch.setattr(api_module, "get_llm_provider", lambda: OpenAIProvider({}))

    status, body = request_json(
        "POST",
        f"/sessions/{session['session_state']['session_id']}/turns",
        {"participant_input": "Vi stänger extern VPN."},
    )

    assert status == 503
    assert "not implemented yet" in body["detail"]


def test_post_turn_returns_502_for_invalid_provider_output(monkeypatch):
    class BadProvider:
        def interpret_action(self, participant_input: str) -> dict:
            return {"action_summary": "x"}

        def generate_narration(self, state) -> dict:
            return {}

    scenario = sample_scenario_payload()
    request_json("POST", "/scenarios", scenario)
    monkeypatch.setattr(api_module, "get_llm_provider", lambda: MockLLMProvider())
    _, session = request_json(
        "POST",
        "/sessions",
        {"scenario_id": "scenario-001", "audience": "krisledning"},
    )
    monkeypatch.setattr(api_module, "get_llm_provider", lambda: BadProvider())

    status, body = request_json(
        "POST",
        f"/sessions/{session['session_state']['session_id']}/turns",
        {"participant_input": "Vi stänger extern VPN."},
    )

    assert status == 502
    assert body["detail"] == "Invalid interpreted action payload"


def test_post_turn_returns_retry_metadata_for_retryable_provider_500(monkeypatch):
    class FlakyProvider:
        def interpret_action(self, participant_input: str) -> dict:
            raise ProviderUpstreamError(
                "Ollama request failed during interpret_action with upstream status 500: upstream failure",
                provider_stage="interpret_action",
                upstream_status_code=500,
                retryable=True,
            )

        def generate_narration(self, state) -> dict:
            return {}

    scenario = sample_scenario_payload()
    request_json("POST", "/scenarios", scenario)
    monkeypatch.setattr(api_module, "get_llm_provider", lambda: MockLLMProvider())
    _, session = request_json(
        "POST",
        "/sessions",
        {"scenario_id": "scenario-001", "audience": "krisledning"},
    )
    monkeypatch.setattr(api_module, "get_llm_provider", lambda: FlakyProvider())

    status, body = request_json(
        "POST",
        f"/sessions/{session['session_state']['session_id']}/turns",
        {"participant_input": "Vi stänger extern VPN."},
    )

    assert status == 502
    assert body["error_code"] == "llm_provider_retryable_failure"
    assert body["retryable"] is True
    assert body["retry_after_seconds"] == 2
    assert body["attempt"] == 1
    assert body["max_attempts"] == 5
    assert body["provider_stage"] == "interpret_action"
    assert body["upstream_status_code"] == 500


def test_post_turn_returns_retry_metadata_for_retryable_provider_503(monkeypatch):
    class FlakyProvider:
        def interpret_action(self, participant_input: str) -> dict:
            return MockLLMProvider().interpret_action(participant_input)

        def generate_narration(self, state) -> dict:
            raise ProviderUpstreamError(
                "Ollama request failed during generate_narration with upstream status 503: service unavailable",
                provider_stage="generate_narration",
                upstream_status_code=503,
                retryable=True,
            )

    scenario = sample_scenario_payload()
    request_json("POST", "/scenarios", scenario)
    monkeypatch.setattr(api_module, "get_llm_provider", lambda: MockLLMProvider())
    _, session = request_json(
        "POST",
        "/sessions",
        {"scenario_id": "scenario-001", "audience": "krisledning"},
    )
    monkeypatch.setattr(api_module, "get_llm_provider", lambda: FlakyProvider())

    status, body = request_json(
        "POST",
        f"/sessions/{session['session_state']['session_id']}/turns",
        {"participant_input": "Vi stänger extern VPN."},
    )

    assert status == 502
    assert body["error_code"] == "llm_provider_retryable_failure"
    assert body["retryable"] is True
    assert body["provider_stage"] == "generate_narration"
    assert body["upstream_status_code"] == 503


def test_post_turn_returns_retry_metadata_for_retryable_provider_504(monkeypatch):
    class FlakyProvider:
        def interpret_action(self, participant_input: str) -> dict:
            raise ProviderUpstreamError(
                "Ollama request failed during interpret_action with upstream status 504: gateway timeout",
                provider_stage="interpret_action",
                upstream_status_code=504,
                retryable=True,
            )

        def generate_narration(self, state) -> dict:
            return {}

    scenario = sample_scenario_payload()
    request_json("POST", "/scenarios", scenario)
    monkeypatch.setattr(api_module, "get_llm_provider", lambda: MockLLMProvider())
    _, session = request_json(
        "POST",
        "/sessions",
        {"scenario_id": "scenario-001", "audience": "krisledning"},
    )
    monkeypatch.setattr(api_module, "get_llm_provider", lambda: FlakyProvider())

    status, body = request_json(
        "POST",
        f"/sessions/{session['session_state']['session_id']}/turns",
        {"participant_input": "Vi stänger extern VPN."},
    )

    assert status == 502
    assert body["error_code"] == "llm_provider_retryable_failure"
    assert body["retryable"] is True
    assert body["upstream_status_code"] == 504


def test_post_turn_returns_non_retryable_metadata_for_provider_400(monkeypatch):
    class ClientErrorProvider:
        def interpret_action(self, participant_input: str) -> dict:
            raise ProviderUpstreamError(
                "Ollama request failed during interpret_action with upstream status 400: bad request",
                provider_stage="interpret_action",
                upstream_status_code=400,
                retryable=False,
            )

        def generate_narration(self, state) -> dict:
            return {}

    scenario = sample_scenario_payload()
    request_json("POST", "/scenarios", scenario)
    monkeypatch.setattr(api_module, "get_llm_provider", lambda: MockLLMProvider())
    _, session = request_json(
        "POST",
        "/sessions",
        {"scenario_id": "scenario-001", "audience": "krisledning"},
    )
    monkeypatch.setattr(api_module, "get_llm_provider", lambda: ClientErrorProvider())

    status, body = request_json(
        "POST",
        f"/sessions/{session['session_state']['session_id']}/turns",
        {"participant_input": "Vi stänger extern VPN."},
    )

    assert status == 502
    assert body["error_code"] == "llm_provider_upstream_failure"
    assert body["retryable"] is False
    assert body["retry_after_seconds"] is None
    assert body["upstream_status_code"] == 400


def test_get_timeline_returns_turns_in_order(monkeypatch):
    monkeypatch.setattr(api_module, "get_llm_provider", lambda: MockLLMProvider())

    scenario = sample_scenario_payload()
    request_json("POST", "/scenarios", scenario)
    _, session = request_json(
        "POST",
        "/sessions",
        {"scenario_id": "scenario-001", "audience": "krisledning"},
    )

    request_json(
        "POST",
        f"/sessions/{session['session_state']['session_id']}/turns",
        {"participant_input": "Vi stänger extern VPN."},
    )
    request_json(
        "POST",
        f"/sessions/{session['session_state']['session_id']}/turns",
        {"participant_input": "Vi går ut med ett första uttalande."},
    )

    status, body = request_json(
        "GET", f"/sessions/{session['session_state']['session_id']}/timeline"
    )

    assert status == 200
    assert [turn["turn_number"] for turn in body] == [1, 2]
    assert body[0]["participant_input"] == "Vi stänger extern VPN."
    assert body[1]["participant_input"] == "Vi går ut med ett första uttalande."


def test_get_timeline_includes_complete_turn_data(monkeypatch):
    monkeypatch.setattr(api_module, "get_llm_provider", lambda: MockLLMProvider())

    scenario = sample_scenario_payload()
    request_json("POST", "/scenarios", scenario)
    _, session = request_json(
        "POST",
        "/sessions",
        {"scenario_id": "scenario-001", "audience": "krisledning"},
    )

    request_json(
        "POST",
        f"/sessions/{session['session_state']['session_id']}/turns",
        {
            "participant_input": "Vi stänger extern VPN och samlar incidentledningsgruppen."
        },
    )

    status, body = request_json(
        "GET", f"/sessions/{session['session_state']['session_id']}/timeline"
    )

    assert status == 200
    assert len(body) == 1
    assert body[0]["interpreted_action"]["action_types"]
    assert (
        body[0]["state_snapshot"]["session_id"]
        == session["session_state"]["session_id"]
    )
    assert body[0]["narrator_response"]["facilitator_notes"]


def test_complete_session_returns_debrief_and_marks_session_completed(monkeypatch):
    monkeypatch.setattr(api_module, "get_llm_provider", lambda: MockLLMProvider())

    scenario = sample_scenario_payload()
    request_json("POST", "/scenarios", scenario)
    _, session = request_json(
        "POST",
        "/sessions",
        {"scenario_id": "scenario-001", "audience": "krisledning"},
    )

    request_json(
        "POST",
        f"/sessions/{session['session_state']['session_id']}/turns",
        {"participant_input": "Vi stänger extern VPN."},
    )

    status, body = request_json(
        "POST",
        f"/sessions/{session['session_state']['session_id']}/complete",
    )

    assert status == 200
    assert body["session_state"]["status"] == "completed"
    assert body["debrief"]["exercise_summary"]
    assert body["debrief"]["timeline_summary"]
    assert body["debrief"]["debrief_questions"]


def test_complete_session_rejects_empty_timeline(monkeypatch):
    monkeypatch.setattr(api_module, "get_llm_provider", lambda: MockLLMProvider())

    scenario = sample_scenario_payload()
    request_json("POST", "/scenarios", scenario)
    _, session = request_json(
        "POST",
        "/sessions",
        {"scenario_id": "scenario-001", "audience": "krisledning"},
    )

    status, body = request_json(
        "POST",
        f"/sessions/{session['session_state']['session_id']}/complete",
    )

    assert status == 400
    assert "at least one turn" in body["detail"]


def test_post_turn_rejects_completed_session(monkeypatch):
    monkeypatch.setattr(api_module, "get_llm_provider", lambda: MockLLMProvider())

    scenario = sample_scenario_payload()
    request_json("POST", "/scenarios", scenario)
    _, session = request_json(
        "POST",
        "/sessions",
        {"scenario_id": "scenario-001", "audience": "krisledning"},
    )

    request_json(
        "POST",
        f"/sessions/{session['session_state']['session_id']}/turns",
        {"participant_input": "Vi stänger extern VPN."},
    )
    request_json(
        "POST",
        f"/sessions/{session['session_state']['session_id']}/complete",
    )

    status, body = request_json(
        "POST",
        f"/sessions/{session['session_state']['session_id']}/turns",
        {"participant_input": "Vi går ut med ett uttalande."},
    )

    assert status == 409
    assert "not active" in body["detail"]
