import asyncio
import json

from src import api as api_module
from src.main import app
from src.services import reporting as reporting_service
from src.services.llm_provider import (
    OpenAIProvider,
    ProviderResponseFormatError,
    ProviderUpstreamError,
)
from tests.mock_llm_provider import MockLLMProvider


def request_json(method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    status, _, response_body = request_response(method, path, body=body)
    parsed_body = json.loads(response_body) if response_body else {}
    return status, parsed_body


def request_response(
    method: str, path: str, body: dict | None = None
) -> tuple[int, dict[str, str], bytes]:
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
    headers = {
        key.decode("latin-1"): value.decode("latin-1")
        for key, value in messages[0].get("headers", [])
    }
    response_body = b"".join(
        message.get("body", b"")
        for message in messages
        if message["type"] == "http.response.body"
    )
    return status, headers, response_body


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
        "states": [
            {
                "id": "state-initial-detection",
                "phase": "initial-detection",
                "title": "Initial detection",
                "description": "Det första scenläget för API-testet.",
                "time": "08:15",
                "known_facts": ["Inloggningsproblem"],
                "unknowns": ["Omfattning oklar"],
                "affected_systems": ["AD"],
                "business_impact": ["Intern påverkan"],
                "impact_level": 2,
                "narration": {
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
            {
                "id": "state-containment",
                "phase": "containment",
                "title": "Containment",
                "description": "Containment-läget för API-testet.",
            },
        ],
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
    payload["text_matchers"] = [
        {
            "id": "matcher-containment-external-access",
            "field": "action.action_types",
            "match_type": "contains_any",
            "patterns": ["extern åtkomst", "extern access", "vpn"],
            "value": "containment",
        }
    ]
    payload["interpretation_hints"] = [
        {
            "id": "hint-target-external-access",
            "when": {
                "action_types_contains": ["containment"],
                "text_contains_any": ["extern åtkomst", "extern access", "vpn"],
            },
            "add_targets": ["external_access"],
        }
    ]
    payload["target_aliases"] = [
        {
            "id": "alias-external-access",
            "canonical": "external_access",
            "aliases": ["extern åtkomst", "externa anslutningar", "vpn"],
        }
    ]
    payload["states"][1].update(
        {
            "known_facts": ["Extern åtkomst har begränsats."],
            "unknowns": ["Om angriparen har alternativ åtkomst."],
            "affected_systems": ["VPN", "Federerade inloggningar"],
            "business_impact": ["Extern serviceleverans påverkas."],
            "narration": {
                "default": {
                    "situation_update": "Kl. 08:30 har ni gått in i en tydlig containmentfas. Extern åtkomst har begränsats för att minska angriparens handlingsutrymme, men åtgärden skapar omedelbart följdeffekter i verksamheten.",
                    "key_points": [
                        "Extern åtkomst har begränsats för att minska fortsatt spridning.",
                        "Verksamhetspåverkan ökar när externa tjänster och fjärrarbete störs.",
                    ],
                    "new_consequences": [
                        "Externa användare och leverantörer får svårare att nå systemen."
                    ],
                    "injects": [],
                    "decisions_to_consider": [
                        "Hur länge kan begränsningarna ligga kvar?"
                    ],
                    "facilitator_notes": "Fördefinierat containmentnarrativ för API-testet.",
                }
            },
        }
    )
    payload["inject_catalog"] = [
        {
            "id": "inject-media-001",
            "type": "media",
            "title": "Frågor från lokalmedia",
            "description": "Lokalmedia vill ha en kommentar inom 20 minuter.",
            "trigger_conditions": ["Stigande medietryck"],
            "audience_relevance": ["krisledning"],
            "severity": 3,
        },
        {
            "id": "inject-ops-001",
            "type": "operations",
            "title": "Verksamhetssystem slutar fungera",
            "description": "Ett verksamhetskritiskt system går inte längre att använda.",
            "trigger_conditions": ["Ökad störningsnivå"],
            "audience_relevance": ["krisledning"],
            "severity": 4,
        },
    ]
    payload["executable_rules"] = [
        {
            "id": "rule-restrict-external-access",
            "name": "Markera begränsad extern åtkomst",
            "trigger": "turn_processed",
            "conditions": [
                {
                    "fact": "action.action_types",
                    "operator": "contains",
                    "value": "containment",
                },
                {
                    "fact": "action.targets",
                    "operator": "contains",
                    "value": "external_access",
                },
            ],
            "effects": [
                {
                    "type": "set_flag",
                    "flag": "state.flags.external_access_restricted",
                    "value": True,
                },
                {
                    "type": "increment_metric",
                    "metric": "state.metrics.attack_surface",
                    "amount": -1,
                },
                {
                    "type": "increment_metric",
                    "metric": "state.metrics.service_disruption",
                    "amount": 1,
                },
                {
                    "type": "append_consequence",
                    "item": "Begränsad extern åtkomst minskar attackytan men påverkar externa tjänster.",
                },
                {
                    "type": "append_focus_item",
                    "item": "Hantera påverkan på externa tjänster.",
                },
                {
                    "type": "append_exercise_log",
                    "log_type": "system_consequence",
                    "message": "Extern attackyta minskar, men tjänstepåverkan ökar externt.",
                },
            ],
            "priority": "high",
            "once": True,
        },
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


def enrichment_driven_scenario_payload():
    payload = sample_scenario_payload()
    payload["text_matchers"] = [
        {
            "id": "matcher-containment",
            "field": "action.action_types",
            "match_type": "contains_any",
            "patterns": ["extern åtkomst", "extern access"],
            "value": "containment",
        }
    ]
    payload["interpretation_hints"] = [
        {
            "id": "hint-external-access",
            "when": {
                "action_types_contains": ["containment"],
                "text_contains_any": ["extern åtkomst", "extern access"],
            },
            "add_targets": ["external_access"],
        }
    ]
    payload["target_aliases"] = [
        {
            "id": "alias-external-access",
            "canonical": "external_access",
            "aliases": ["extern åtkomst", "externa anslutningar"],
        }
    ]
    payload["executable_rules"] = [
        {
            "id": "rule-restrict-external-access",
            "name": "Markera begränsad extern åtkomst",
            "trigger": "turn_processed",
            "conditions": [
                {
                    "fact": "action.action_types",
                    "operator": "contains",
                    "value": "containment",
                },
                {
                    "fact": "action.targets",
                    "operator": "contains",
                    "value": "external_access",
                },
            ],
            "effects": [
                {
                    "type": "set_flag",
                    "flag": "state.flags.external_access_restricted",
                    "value": True,
                }
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
    assert len(body["text_matchers"]) >= 3
    assert len(body["target_aliases"]) >= 3
    assert any(item["id"] == "matcher-target-vpn" for item in body["text_matchers"])
    assert any(item["id"] == "alias-external-access" for item in body["target_aliases"])
    assert any(
        item["id"] == "hint-communication-communications-team"
        for item in body["interpretation_hints"]
    )


def test_frontend_root_redirects_to_setup():
    response = asyncio.run(api_module.frontend())

    assert response.status_code == 307
    assert response.headers["location"] == "/setup"


def test_frontend_setup_page_is_served():
    response = asyncio.run(api_module.frontend_setup())

    assert str(response.path).endswith("frontend/setup.html")


def test_frontend_authoring_page_is_served():
    response = asyncio.run(api_module.frontend_authoring())

    assert str(response.path).endswith("frontend/authoring.html")


def test_frontend_session_page_is_served():
    response = asyncio.run(api_module.frontend_session())

    assert str(response.path).endswith("frontend/session.html")


def test_frontend_report_page_is_served():
    response = asyncio.run(api_module.frontend_report())

    assert str(response.path).endswith("frontend/report.html")


def test_frontend_static_assets_are_served():
    assert (api_module.FRONTEND_DIR / "common.js").exists()
    assert (api_module.FRONTEND_DIR / "styles.css").exists()


def test_frontend_report_uses_backend_rendered_report_endpoints():
    report_page = (api_module.FRONTEND_DIR / "report.html").read_text(encoding="utf-8")

    assert "/report.html" in report_page
    assert "/report.md" in report_page
    assert "/report.pdf" in report_page
    assert "DOMParser" in report_page
    assert "dangerouslySetInnerHTML" in report_page
    assert "<iframe" not in report_page


def test_frontend_setup_loads_selected_scenario_from_database_only():
    setup_page = (api_module.FRONTEND_DIR / "setup.html").read_text(encoding="utf-8")

    assert "Common.apiRequest(`/scenarios/${selectedScenarioId}`)" in setup_page
    assert "/sample-scenarios/default" not in setup_page
    assert "Ladda från databasen" not in setup_page


def test_create_and_get_scenario():
    scenario = sample_scenario_payload()

    create_status, create_body = request_json("POST", "/scenarios", scenario)
    get_status, get_body = request_json("GET", "/scenarios/scenario-001")

    assert create_status == 200
    assert create_body["id"] == "scenario-001"
    assert get_status == 200
    assert get_body["title"] == scenario["title"]


def test_generate_scenario_draft_from_text(monkeypatch):
    monkeypatch.setattr(api_module, "get_llm_provider", lambda: MockLLMProvider())

    status, body = request_json(
        "POST",
        "/scenarios/draft-from-text",
        {
            "source_text": "# Scenario\n\nKl. 08:15 rapporteras stora störningar i inloggning och fildelning.",
            "source_format": "markdown",
        },
    )

    assert status == 200
    assert body["id"] == "scenario-draft-001"
    assert body["original_text"].startswith("# Scenario")
    assert body["states"][0]["phase"] == "initial-detection"
    assert _contains_none(body) is False


def test_generated_scenario_draft_can_be_saved_without_null_cleanup(monkeypatch):
    monkeypatch.setattr(api_module, "get_llm_provider", lambda: MockLLMProvider())

    draft_status, draft_body = request_json(
        "POST",
        "/scenarios/draft-from-text",
        {
            "source_text": "# Scenario\n\nKl. 08:15 rapporteras stora störningar i inloggning och fildelning.",
            "source_format": "markdown",
        },
    )
    save_status, save_body = request_json("POST", "/scenarios", draft_body)

    assert draft_status == 200
    assert save_status == 200
    assert save_body["id"] == draft_body["id"]


def _contains_none(value):
    if value is None:
        return True
    if isinstance(value, dict):
        return any(_contains_none(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_none(item) for item in value)
    return False


def test_generate_scenario_draft_from_text_rejects_invalid_provider_output(monkeypatch):
    class BadProvider(MockLLMProvider):
        def generate_scenario_draft(
            self, source_text: str, source_format: str = "markdown"
        ) -> dict:
            return {"id": "broken"}

    monkeypatch.setattr(api_module, "get_llm_provider", lambda: BadProvider())

    status, body = request_json(
        "POST",
        "/scenarios/draft-from-text",
        {
            "source_text": "# Scenario\n\nKl. 08:15 rapporteras stora störningar i inloggning och fildelning.",
            "source_format": "markdown",
        },
    )

    assert status == 502
    assert body["detail"] == "Invalid scenario payload"


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
    scenario["states"][0]["narration"]["by_audience"] = {
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
    scenario["states"][0]["narration"]["by_audience"] = {
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
    assert body["state_snapshot"]["affected_systems"] == [
        "VPN",
        "Federerade inloggningar",
    ]
    assert (
        "Berorda system: VPN, Federerade inloggningar."
        in body["narrator_response"]["key_points"]
    )


def test_post_turn_applies_scenario_action_enrichment_before_rules(monkeypatch):
    class SparseInterpretationProvider(MockLLMProvider):
        def interpret_action(self, participant_input: str) -> dict:
            return {
                "action_summary": "Sparsam tolkning for att testa scenario-driven enrichment.",
                "action_types": ["monitoring"],
                "targets": [],
                "intent": "Testa att scenariot kompletterar tolkningen.",
                "expected_effects": [],
                "risks": [],
                "uncertainties": [],
                "priority": "high",
                "confidence": 0.6,
            }

    monkeypatch.setattr(
        api_module,
        "get_llm_provider",
        lambda: SparseInterpretationProvider(),
    )
    request_json("POST", "/scenarios", enrichment_driven_scenario_payload())
    _, session = request_json(
        "POST",
        "/sessions",
        {"scenario_id": "scenario-001", "audience": "krisledning"},
    )

    status, body = request_json(
        "POST",
        f"/sessions/{session['session_state']['session_id']}/turns",
        {"participant_input": "Vi beslutar att stänga extern åtkomst omedelbart."},
    )

    assert status == 200
    assert body["state_snapshot"]["phase"] == "containment"
    assert any(
        item["type"] == "interpretation_support"
        and item["text"] == "Textmatchning träffade: matcher-containment"
        for item in body["state_snapshot"]["exercise_log"]
    )
    assert any(
        item["type"] == "interpretation_support"
        and item["text"]
        == "Target normaliserad: extern åtkomst -> external_access (alias-external-access)"
        for item in body["state_snapshot"]["exercise_log"]
    )


def test_post_turn_normalizes_provider_targets_with_scenario_aliases(monkeypatch):
    class HumanLabelProvider(MockLLMProvider):
        def interpret_action(self, participant_input: str) -> dict:
            return {
                "action_summary": "Provider returnerar mänskliga labels för targets.",
                "action_types": ["containment"],
                "targets": [
                    "Intern infrastruktur",
                    "Externa nätverksanslutningar",
                ],
                "intent": "Blockera angriparens externa väg in.",
                "expected_effects": [],
                "risks": [],
                "uncertainties": [],
                "priority": "high",
                "confidence": 0.7,
            }

    monkeypatch.setattr(api_module, "get_llm_provider", lambda: HumanLabelProvider())
    request_json("POST", "/scenarios", enrichment_driven_scenario_payload())
    _, session = request_json(
        "POST",
        "/sessions",
        {"scenario_id": "scenario-001", "audience": "krisledning"},
    )

    status, body = request_json(
        "POST",
        f"/sessions/{session['session_state']['session_id']}/turns",
        {"participant_input": "Blockera extern åtkomst."},
    )

    assert status == 200
    assert body["state_snapshot"]["phase"] == "containment"
    assert any(
        item["type"] == "interpretation_support"
        and item["text"]
        == "Target normaliserad: Externa nätverksanslutningar -> external_access (alias-external-access)"
        for item in body["state_snapshot"]["exercise_log"]
    )
    assert body["state_snapshot"]["flags"]["external_access_restricted"] is True


def test_default_sample_scenario_enrichment_supports_communication_and_escalation(
    monkeypatch,
):
    class SparseInterpretationProvider(MockLLMProvider):
        def interpret_action(self, participant_input: str) -> dict:
            return {
                "action_summary": "Sparsam tolkning for att testa sample scenario enrichment.",
                "action_types": ["monitoring"],
                "targets": [],
                "intent": "Testa att samplescenariot kompletterar tolkningen.",
                "expected_effects": [],
                "risks": [],
                "uncertainties": [],
                "priority": "high",
                "confidence": 0.6,
            }

    monkeypatch.setattr(
        api_module,
        "get_llm_provider",
        lambda: SparseInterpretationProvider(),
    )
    sample = api_module.load_sample_scenario()
    api_module.scenario_repository.save(sample)
    _, session = request_json(
        "POST",
        "/sessions",
        {
            "scenario_id": sample.id,
            "audience": "krisledning",
        },
    )

    status, body = request_json(
        "POST",
        f"/sessions/{session['session_state']['session_id']}/turns",
        {
            "participant_input": "Krisledningsgruppen ansvarar för kommunikation till allmänhet, media och myndigheter."
        },
    )

    assert status == 200
    assert body["state_snapshot"]["flags"]["executive_escalation"] is True
    assert body["state_snapshot"]["flags"]["external_comms_sent"] is True
    assert (
        "Förbered ledningsbeslut och eskalering."
        in body["state_snapshot"]["focus_items"]
    )
    assert (
        "Samordna fortsatt extern kommunikation."
        in body["state_snapshot"]["focus_items"]
    )
    assert any(
        item["type"] == "interpretation_support"
        and item["text"] == "Interpretation hint använd: hint-escalation-executive-team"
        for item in body["state_snapshot"]["exercise_log"]
    )
    assert any(
        item["type"] == "interpretation_support"
        and item["text"]
        == "Interpretation hint använd: hint-communication-communications-team"
        for item in body["state_snapshot"]["exercise_log"]
    )


def test_post_turn_uses_scenario_authored_narration_for_full_state(monkeypatch):
    class NarrationMustNotBeGeneratedProvider(MockLLMProvider):
        def generate_narration(self, state):  # pragma: no cover - defensive
            raise AssertionError(
                "generate_narration should not be called for full scenario states"
            )

    monkeypatch.setattr(
        api_module,
        "get_llm_provider",
        lambda: NarrationMustNotBeGeneratedProvider(),
    )
    scenario = sample_scenario_payload()
    scenario["states"].append(
        {
            "id": "state-escalation",
            "phase": "escalation",
            "title": "Escalation",
            "description": "Laget har eskalerat och kraver tydliga ledningsbeslut.",
            "time": "08:45",
            "known_facts": ["Skadan ar mer omfattande an tidigare antaget."],
            "unknowns": [
                "Om angriparen fortfarande har kontroll over centrala system."
            ],
            "affected_systems": ["AD", "Fildelning"],
            "business_impact": ["Fler verksamheter far tydlig driftstorning."],
            "impact_level": 4,
            "narration": {
                "default": {
                    "situation_update": "Laget har eskalerat och tydliga tecken på spridning mellan centrala miljoer har nu konstaterats.",
                    "key_points": [
                        "Ledningen behover fatta samordnade beslut om prioriteringar.",
                        "Teknisk och verksamhetsmassig paverkan okar samtidigt.",
                    ],
                    "new_consequences": [
                        "Fler beroenden mellan verksamheter borjar ge foljdeffekter."
                    ],
                    "injects": [],
                    "decisions_to_consider": [
                        "Behovs ytterligare eskalering till kommunledningen nu?"
                    ],
                    "facilitator_notes": "Detta narrativ ar forfattat direkt i scenario state-escalation.",
                }
            },
        }
    )
    scenario["executable_rules"] = [
        {
            "id": "rule-mark-executive-escalation",
            "name": "Markera eskalering till ledning",
            "trigger": "turn_processed",
            "conditions": [
                {
                    "fact": "action.action_types",
                    "operator": "contains",
                    "value": "escalation",
                }
            ],
            "effects": [
                {
                    "type": "set_flag",
                    "flag": "state.flags.executive_escalation",
                    "value": True,
                }
            ],
            "priority": "high",
            "once": True,
        },
        {
            "id": "rule-phase-escalation",
            "name": "Byt till escalation vid eskalering till ledning",
            "trigger": "turn_processed",
            "conditions": [
                {
                    "fact": "state.flags.executive_escalation",
                    "operator": "equals",
                    "value": True,
                }
            ],
            "effects": [{"type": "set_phase", "phase": "escalation"}],
            "priority": "high",
            "once": True,
        },
    ]
    request_json("POST", "/scenarios", scenario)
    _, session = request_json(
        "POST",
        "/sessions",
        {"scenario_id": "scenario-001", "audience": "krisledning"},
    )

    status, body = request_json(
        "POST",
        f"/sessions/{session['session_state']['session_id']}/turns",
        {"participant_input": "Vi eskalerar till ledningen och kallar in it-chef."},
    )

    assert status == 200
    assert body["state_snapshot"]["phase"] == "escalation"
    assert body["state_snapshot"]["current_time"] == "08:45"
    assert body["state_snapshot"]["known_facts"] == [
        "Skadan ar mer omfattande an tidigare antaget."
    ]
    assert body["narrator_response"]["situation_update"] == (
        "Laget har eskalerat och tydliga tecken på spridning mellan centrala miljoer har nu konstaterats."
    )


def test_post_turn_handles_partial_state_without_optional_runtime_fields(monkeypatch):
    monkeypatch.setattr(api_module, "get_llm_provider", lambda: MockLLMProvider())
    scenario = sample_scenario_payload()
    scenario["states"].append(
        {
            "id": "state-recovery",
            "phase": "recovery",
            "title": "Recovery",
            "description": "Aterhamtning pagar men state saknar frivilliga runtime-falt.",
        }
    )
    scenario["executable_rules"] = [
        {
            "id": "rule-start-forensic-analysis",
            "name": "Markera påbörjad forensisk analys",
            "trigger": "turn_processed",
            "conditions": [
                {
                    "fact": "action.action_types",
                    "operator": "contains",
                    "value": "analysis",
                }
            ],
            "effects": [
                {
                    "type": "set_flag",
                    "flag": "state.flags.forensic_analysis_started",
                    "value": True,
                }
            ],
            "priority": "high",
            "once": True,
        },
        {
            "id": "rule-phase-recovery",
            "name": "Byt till recovery efter analys",
            "trigger": "turn_processed",
            "conditions": [
                {
                    "fact": "state.flags.forensic_analysis_started",
                    "operator": "equals",
                    "value": True,
                }
            ],
            "effects": [{"type": "set_phase", "phase": "recovery"}],
            "priority": "high",
            "once": True,
        },
    ]
    request_json("POST", "/scenarios", scenario)
    _, session = request_json(
        "POST",
        "/sessions",
        {"scenario_id": "scenario-001", "audience": "krisledning"},
    )

    status, body = request_json(
        "POST",
        f"/sessions/{session['session_state']['session_id']}/turns",
        {"participant_input": "Vi startar forensisk analys omgaende."},
    )

    assert status == 200
    assert body["state_snapshot"]["phase"] == "recovery"
    assert body["state_snapshot"]["affected_systems"] == ["AD"]
    assert body["narrator_response"]["key_points"]


def test_post_turn_trims_provider_narration_lists_instead_of_returning_502(
    monkeypatch,
):
    class OverlongNarrationProvider(MockLLMProvider):
        def generate_narration(self, state):
            payload = super().generate_narration(state)
            payload["key_points"] = ["A", "B", "C", "D", "E", "F"]
            payload["injects"] = [
                {"type": "media", "title": "I1", "message": "Inject ett."},
                {"type": "operations", "title": "I2", "message": "Inject tva."},
                {"type": "executive", "title": "I3", "message": "Inject tre."},
            ]
            return payload

    monkeypatch.setattr(
        api_module,
        "get_llm_provider",
        lambda: OverlongNarrationProvider(),
    )
    request_json("POST", "/scenarios", sample_scenario_payload())
    _, session = request_json(
        "POST",
        "/sessions",
        {"scenario_id": "scenario-001", "audience": "krisledning"},
    )

    status, body = request_json(
        "POST",
        f"/sessions/{session['session_state']['session_id']}/turns",
        {"participant_input": "Vi fortsatter att overvaka laget."},
    )

    assert status == 200
    assert body["narrator_response"]["key_points"] == ["A", "B", "C", "D", "E"]
    assert len(body["narrator_response"]["injects"]) == 2


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
    assert body["session_state"]["phase"] == "containment"
    assert body["session_state"]["affected_systems"] == [
        "VPN",
        "Federerade inloggningar",
    ]
    assert body["narration"]["situation_update"].startswith(
        "Kl. 08:30 har ni gått in i en tydlig containmentfas."
    )
    assert any(
        item["text"] == "Manuellt fasbyte: initial-detection -> containment"
        for item in body["session_state"]["exercise_log"]
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


def test_manual_inject_trigger_updates_session_when_inject_is_defined(monkeypatch):
    monkeypatch.setattr(api_module, "get_llm_provider", lambda: MockLLMProvider())
    request_json("POST", "/scenarios", datadriven_scenario_payload())
    _, session = request_json(
        "POST",
        "/sessions",
        {"scenario_id": "scenario-001", "audience": "krisledning"},
    )

    status, body = request_json(
        "POST",
        f"/sessions/{session['session_state']['session_id']}/injects",
        {"inject_id": "inject-media-001"},
    )

    assert status == 200
    assert "inject-media-001" in body["active_injects"]
    assert any(
        item["text"]
        == "Manuellt inject aktiverat: Frågor från lokalmedia (inject-media-001)"
        for item in body["exercise_log"]
    )


def test_manual_inject_trigger_rejects_undefined_inject(monkeypatch):
    monkeypatch.setattr(api_module, "get_llm_provider", lambda: MockLLMProvider())
    request_json("POST", "/scenarios", datadriven_scenario_payload())
    _, session = request_json(
        "POST",
        "/sessions",
        {"scenario_id": "scenario-001", "audience": "krisledning"},
    )

    status, body = request_json(
        "POST",
        f"/sessions/{session['session_state']['session_id']}/injects",
        {"inject_id": "inject-unknown-001"},
    )

    assert status == 400
    assert body["detail"] == "Inject is not defined in the scenario"


def test_manual_inject_trigger_rejects_inactive_session(monkeypatch):
    monkeypatch.setattr(api_module, "get_llm_provider", lambda: MockLLMProvider())
    request_json("POST", "/scenarios", datadriven_scenario_payload())
    _, session = request_json(
        "POST",
        "/sessions",
        {"scenario_id": "scenario-001", "audience": "krisledning"},
    )
    session_id = session["session_state"]["session_id"]
    stored_session = api_module.session_repository.get(session_id)
    assert stored_session is not None
    api_module.session_repository.save(
        stored_session.model_copy(update={"status": "completed"})
    )

    status, body = request_json(
        "POST",
        f"/sessions/{session_id}/injects",
        {"inject_id": "inject-media-001"},
    )

    assert status == 409
    assert body["detail"] == "Session is not active and injects cannot be triggered"


def test_manual_inject_trigger_skips_when_inject_is_already_active(monkeypatch):
    monkeypatch.setattr(api_module, "get_llm_provider", lambda: MockLLMProvider())
    request_json("POST", "/scenarios", datadriven_scenario_payload())
    _, session = request_json(
        "POST",
        "/sessions",
        {"scenario_id": "scenario-001", "audience": "krisledning"},
    )
    session_id = session["session_state"]["session_id"]

    first_status, first_body = request_json(
        "POST",
        f"/sessions/{session_id}/injects",
        {"inject_id": "inject-media-001"},
    )
    second_status, second_body = request_json(
        "POST",
        f"/sessions/{session_id}/injects",
        {"inject_id": "inject-media-001"},
    )

    assert first_status == 200
    assert second_status == 200
    assert second_body["active_injects"].count("inject-media-001") == 1
    assert (
        sum(
            1
            for item in second_body["exercise_log"]
            if item["text"]
            == "Manuellt inject aktiverat: Frågor från lokalmedia (inject-media-001)"
        )
        == 1
    )


def test_manual_inject_trigger_reactivates_resolved_inject(monkeypatch):
    monkeypatch.setattr(api_module, "get_llm_provider", lambda: MockLLMProvider())
    request_json("POST", "/scenarios", datadriven_scenario_payload())
    _, session = request_json(
        "POST",
        "/sessions",
        {"scenario_id": "scenario-001", "audience": "krisledning"},
    )
    session_id = session["session_state"]["session_id"]
    stored_session = api_module.session_repository.get(session_id)
    assert stored_session is not None
    api_module.session_repository.save(
        stored_session.model_copy(
            update={
                "active_injects": [],
                "resolved_injects": ["inject-media-001"],
            }
        )
    )

    status, body = request_json(
        "POST",
        f"/sessions/{session_id}/injects",
        {"inject_id": "inject-media-001"},
    )

    assert status == 200
    assert "inject-media-001" in body["active_injects"]
    assert "inject-media-001" not in body["resolved_injects"]
    assert any(
        item["text"]
        == "Manuellt inject återaktiverat: Frågor från lokalmedia (inject-media-001)"
        for item in body["exercise_log"]
    )


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
    assert "OpenRouterProvider requires" in body["detail"]


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


def test_post_turn_returns_retry_metadata_for_provider_response_format_error(
    monkeypatch,
):
    class FormatErrorProvider:
        def interpret_action(self, participant_input: str) -> dict:
            return MockLLMProvider().interpret_action(participant_input)

        def generate_narration(self, state) -> dict:
            raise ProviderResponseFormatError(
                "Ollama response was not valid JSON",
                provider_stage="generate_narration",
                raw_response_excerpt='{"broken": true "oops"}',
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
    monkeypatch.setattr(api_module, "get_llm_provider", lambda: FormatErrorProvider())

    status, body = request_json(
        "POST",
        f"/sessions/{session['session_state']['session_id']}/turns",
        {"participant_input": "Vi stänger extern VPN."},
    )

    assert status == 502
    assert body["error_code"] == "llm_provider_retryable_failure"
    assert body["retryable"] is True
    assert body["retry_after_seconds"] == 2
    assert body["provider_stage"] == "generate_narration"
    assert body["upstream_status_code"] is None


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
    assert api_module.session_repository.get_report(
        session["session_state"]["session_id"]
    )


def test_get_session_report_markdown_returns_generated_report(monkeypatch):
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

    status, headers, body = request_response(
        "GET", f"/sessions/{session['session_state']['session_id']}/report.md"
    )

    assert status == 200
    assert headers["content-type"].startswith("text/markdown")
    report_markdown = body.decode()
    assert "# Scenariorapport:" in report_markdown
    assert "## Scenarioinformation" in report_markdown
    assert "## Slutlig sessionsbild" in report_markdown
    assert "## Debrief-underlag" in report_markdown
    assert "## Summering med tidslinje" in report_markdown
    assert "## Original text" in report_markdown
    assert report_markdown.count("\n---\n") >= 3
    assert report_markdown.index("## Scenarioinformation") < report_markdown.index(
        "## Slutlig sessionsbild"
    )
    assert report_markdown.index("## Slutlig sessionsbild") < report_markdown.index(
        "## Debrief-underlag"
    )
    assert report_markdown.index("## Debrief-underlag") < report_markdown.index(
        "## Summering med tidslinje"
    )
    assert report_markdown.index("## Summering med tidslinje") < report_markdown.index(
        "## Original text"
    )


def test_get_session_report_html_uses_pandoc_renderer(monkeypatch):
    monkeypatch.setattr(api_module, "get_llm_provider", lambda: MockLLMProvider())
    monkeypatch.setattr(
        "src.api.render_markdown_to_html",
        lambda markdown: (
            f"<html><body><h1>{'Scenariorapport' if 'Scenariorapport' in markdown else ''}</h1></body></html>"
        ),
    )

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

    status, headers, body = request_response(
        "GET", f"/sessions/{session['session_state']['session_id']}/report.html"
    )

    assert status == 200
    assert headers["content-type"].startswith("text/html")
    assert "<h1>Scenariorapport</h1>" in body.decode()


def test_get_session_report_pdf_returns_pandoc_output(monkeypatch):
    monkeypatch.setattr(api_module, "get_llm_provider", lambda: MockLLMProvider())
    monkeypatch.setattr(
        "src.api.render_markdown_to_pdf",
        lambda markdown: b"%PDF-1.7\nmock",
    )

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

    status, headers, body = request_response(
        "GET", f"/sessions/{session['session_state']['session_id']}/report.pdf"
    )

    assert status == 200
    assert headers["content-type"] == "application/pdf"
    assert body.startswith(b"%PDF-1.7")


def test_prepare_markdown_for_pandoc_pdf_uses_literal_newpage_for_latex_engines():
    prepared = reporting_service._prepare_markdown_for_pandoc_pdf(
        "## Del 1\n\nText\n\n---\n\n## Del 2\n",
        "xelatex",
    )

    assert "```{=latex}" in prepared
    assert "\\newpage" in prepared
    assert "ewpage" not in prepared.replace("\\newpage", "")


def test_prepare_markdown_for_pandoc_pdf_uses_html_page_break_for_html_engines():
    prepared = reporting_service._prepare_markdown_for_pandoc_pdf(
        "## Del 1\n\nText\n\n---\n\n## Del 2\n",
        "weasyprint",
    )

    assert "page-break-after: always" in prepared
    assert "\\newpage" not in prepared


def test_get_pandoc_from_format_enables_raw_attribute_for_pdf():
    from_format = reporting_service._get_pandoc_from_format(
        ["--to", "pdf", "--output", "-", "--pdf-engine", "pdflatex"]
    )

    assert from_format == "markdown+raw_tex+raw_html+raw_attribute"


def test_get_session_report_pdf_falls_back_without_pandoc_engine(monkeypatch):
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

    monkeypatch.setattr(
        "src.services.reporting.shutil.which",
        lambda name: "/usr/bin/pandoc" if name == "pandoc" else None,
    )

    status, headers, body = request_response(
        "GET", f"/sessions/{session['session_state']['session_id']}/report.pdf"
    )

    assert status == 200
    assert headers["content-type"] == "application/pdf"
    assert body.startswith(b"%PDF")


def test_get_session_report_html_falls_back_when_pandoc_is_unavailable(monkeypatch):
    monkeypatch.setattr(api_module, "get_llm_provider", lambda: MockLLMProvider())
    monkeypatch.setattr(
        "src.services.reporting.shutil.which",
        lambda _: None,
    )

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

    status, headers, body = request_response(
        "GET",
        f"/sessions/{session['session_state']['session_id']}/report.html",
    )

    assert status == 200
    assert headers["content-type"].startswith("text/html")
    assert "<html" in body.decode()
    assert 'class="panel report-text markdown-content"' in body.decode()
    assert "Scenariorapport" in body.decode()


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
