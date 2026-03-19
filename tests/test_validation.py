import pytest
from pydantic import ValidationError

from src.models.scenario import Scenario
from src.models.session import SessionMetrics, SessionState
from src.models.turn import Turn
from src.schemas.interpreted_action import InterpretedAction
from src.schemas.narrator_response import NarratorResponse


def sample_scenario_dict():
    return {
        "id": "scenario-001",
        "title": "Ransomware mot kommunal verksamhet",
        "version": "1.0",
        "description": "Testscenario",
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
                "description": "De första indikationerna på incidenten samlas in.",
                "time": "08:15",
                "known_facts": ["Inloggningsproblem"],
                "unknowns": ["Omfattning oklar"],
                "affected_systems": ["AD"],
                "business_impact": ["Intern påverkan"],
                "impact_level": 2,
                "narration": {
                    "default": {
                        "situation_update": "Läget är fortsatt osäkert men tillräckligt beskrivet för att starta övningen.",
                        "key_points": [
                            "Flera system påverkas.",
                            "Omfattningen är fortfarande oklar.",
                        ],
                        "new_consequences": [],
                        "injects": [],
                        "decisions_to_consider": ["Behöver vi eskalera läget nu?"],
                        "facilitator_notes": "Fördefinierat startnarrativ.",
                    }
                },
            },
            {
                "id": "state-containment",
                "phase": "containment",
                "title": "Containment",
                "description": "Åtgärder för att begränsa vidare påverkan pågår.",
            },
        ],
        "actors": [],
        "inject_catalog": [],
        "text_matchers": [],
        "target_aliases": [],
        "interpretation_hints": [],
        "rules": [],
        "presentation_guidelines": {
            "krisledning": {"focus": ["beslut"], "tone": "strategisk"},
            "it-ledning": {"focus": ["system"], "tone": "operativ"},
        },
    }


def sample_session_state_dict():
    return {
        "session_id": "sess-1",
        "scenario_id": "scenario-001",
        "scenario_version": "1.0",
        "audience": "krisledning",
        "current_time": "08:15",
        "turn_number": 0,
        "phase": "initial-detection",
        "known_facts": ["Inloggningsproblem"],
        "unknowns": ["Omfattning oklar"],
        "metrics": {
            "impact_level": 2,
            "media_pressure": 0,
            "service_disruption": 0,
            "leadership_pressure": 0,
            "public_confusion": 0,
            "attack_surface": 3,
        },
    }


def sample_interpreted_action_dict():
    return {
        "action_summary": "Stänger extern VPN.",
        "action_types": ["containment"],
        "targets": ["vpn"],
        "intent": "Minska attackytan.",
        "expected_effects": ["Minskar extern exponering."],
        "risks": ["Kan påverka användare."],
        "uncertainties": ["Om angriparen redan har annan åtkomst."],
        "priority": "high",
        "confidence": 0.9,
    }


def sample_narrator_response_dict():
    return {
        "situation_update": "Läget är fortsatt osäkert men under närmare kontroll efter de första åtgärderna.",
        "key_points": ["Attackytan minskar.", "Kommunikationsbehovet ökar."],
        "new_consequences": ["Fjärranvändare påverkas."],
        "injects": [
            {
                "type": "media",
                "title": "Mediefråga",
                "message": "Journalister vill ha en kommentar.",
            }
        ],
        "decisions_to_consider": ["Behöver vi gå ut externt nu?"],
        "facilitator_notes": "Använd responsen för fortsatt diskussion.",
    }


def test_scenario_validation_accepts_valid_payload():
    scenario = Scenario(**sample_scenario_dict())
    assert scenario.id == "scenario-001"
    assert scenario.states[0].impact_level == 2
    assert scenario.executable_rules == []
    assert scenario.states[0].phase == "initial-detection"


def test_scenario_validation_accepts_audience_specific_initial_narration():
    payload = sample_scenario_dict()
    payload["states"][0]["narration"]["by_audience"] = {
        "krisledning": sample_narrator_response_dict()
    }

    scenario = Scenario(**payload)

    assert "krisledning" in scenario.states[0].narration.by_audience


def test_scenario_validation_rejects_missing_initial_narration_sources():
    payload = sample_scenario_dict()
    payload["states"][0]["narration"] = {}

    with pytest.raises(ValidationError):
        Scenario(**payload)


def test_scenario_validation_rejects_empty_audiences():
    payload = sample_scenario_dict()
    payload["audiences"] = []

    with pytest.raises(ValidationError):
        Scenario(**payload)


def test_scenario_validation_rejects_timebox_above_limit():
    payload = sample_scenario_dict()
    payload["timebox_minutes"] = 600

    with pytest.raises(ValidationError):
        Scenario(**payload)


def test_scenario_validation_accepts_executable_rules():
    payload = sample_scenario_dict()
    payload["executable_rules"] = [
        {
            "id": "rule-phase-change",
            "name": "Byt fas vid containment",
            "trigger": "turn_processed",
            "conditions": [
                {
                    "fact": "action.action_types",
                    "operator": "contains",
                    "value": "containment",
                }
            ],
            "effects": [{"type": "set_phase", "phase": "containment"}],
            "priority": "high",
            "once": True,
        }
    ]

    scenario = Scenario(**payload)

    assert scenario.executable_rules[0].trigger == "turn_processed"
    assert scenario.executable_rules[0].effects[0].type == "set_phase"


def test_scenario_validation_accepts_text_matchers_and_interpretation_hints():
    payload = sample_scenario_dict()
    payload["text_matchers"] = [
        {
            "id": "matcher-external-access",
            "field": "action.targets",
            "match_type": "contains_any",
            "patterns": ["extern åtkomst", "vpn"],
            "value": "external_access",
        }
    ]
    payload["interpretation_hints"] = [
        {
            "id": "hint-containment-external-access",
            "when": {
                "action_types_contains": ["containment"],
                "text_contains_any": ["extern åtkomst", "vpn"],
            },
            "add_targets": ["external_access"],
        }
    ]

    scenario = Scenario(**payload)

    assert scenario.text_matchers[0].field == "action.targets"
    assert scenario.interpretation_hints[0].add_targets == ["external_access"]


def test_scenario_validation_accepts_target_aliases():
    payload = sample_scenario_dict()
    payload["target_aliases"] = [
        {
            "id": "alias-external-access",
            "canonical": "external_access",
            "aliases": ["extern åtkomst", "externa anslutningar"],
        }
    ]

    scenario = Scenario(**payload)

    assert scenario.target_aliases[0].canonical == "external_access"


def test_scenario_validation_rejects_duplicate_target_alias_ids():
    payload = sample_scenario_dict()
    payload["target_aliases"] = [
        {
            "id": "alias-duplicate",
            "canonical": "external_access",
            "aliases": ["extern åtkomst"],
        },
        {
            "id": "alias-duplicate",
            "canonical": "vpn",
            "aliases": ["vpn"],
        },
    ]

    with pytest.raises(ValidationError):
        Scenario(**payload)


def test_scenario_validation_rejects_invalid_text_matcher_field():
    payload = sample_scenario_dict()
    payload["text_matchers"] = [
        {
            "id": "matcher-invalid",
            "field": "state.phase",
            "match_type": "contains_any",
            "patterns": ["containment"],
            "value": "containment",
        }
    ]

    with pytest.raises(ValidationError):
        Scenario(**payload)


def test_scenario_validation_rejects_interpretation_hint_without_conditions():
    payload = sample_scenario_dict()
    payload["interpretation_hints"] = [
        {
            "id": "hint-empty",
            "when": {},
            "add_targets": ["external_access"],
        }
    ]

    with pytest.raises(ValidationError):
        Scenario(**payload)


def test_scenario_validation_rejects_interpretation_hint_without_effects():
    payload = sample_scenario_dict()
    payload["interpretation_hints"] = [
        {
            "id": "hint-no-effects",
            "when": {"text_contains_any": ["extern åtkomst"]},
        }
    ]

    with pytest.raises(ValidationError):
        Scenario(**payload)


def test_scenario_validation_rejects_duplicate_state_phases():
    payload = sample_scenario_dict()
    payload["states"][1]["phase"] = "initial-detection"

    with pytest.raises(ValidationError):
        Scenario(**payload)


def test_scenario_validation_rejects_set_phase_not_in_phase_list():
    payload = sample_scenario_dict()
    payload["executable_rules"] = [
        {
            "id": "rule-phase-change",
            "name": "Byt till escalation",
            "trigger": "turn_processed",
            "effects": [{"type": "set_phase", "phase": "escalation"}],
        }
    ]

    with pytest.raises(ValidationError):
        Scenario(**payload)


def test_scenario_validation_accepts_no_communication_turns_as_rule_fact():
    payload = sample_scenario_dict()
    payload["executable_rules"] = [
        {
            "id": "rule-missing-comms",
            "name": "Utebliven kommunikation ökar trycket",
            "trigger": "turn_processed",
            "conditions": [
                {
                    "fact": "state.no_communication_turns",
                    "operator": "gte",
                    "value": 2,
                }
            ],
            "effects": [
                {
                    "type": "increment_metric",
                    "metric": "state.metrics.media_pressure",
                    "amount": 1,
                }
            ],
        }
    ]

    scenario = Scenario(**payload)

    assert (
        scenario.executable_rules[0].conditions[0].fact
        == "state.no_communication_turns"
    )


def test_scenario_validation_rejects_invalid_executable_rule_operator():
    payload = sample_scenario_dict()
    payload["executable_rules"] = [
        {
            "id": "rule-invalid",
            "name": "Ogiltig operator",
            "trigger": "turn_processed",
            "conditions": [
                {
                    "fact": "state.phase",
                    "operator": "matches",
                    "value": "containment",
                }
            ],
            "effects": [{"type": "set_phase", "phase": "containment"}],
        }
    ]

    with pytest.raises(ValidationError):
        Scenario(**payload)


def test_session_state_validation_accepts_valid_payload():
    state = SessionState(**sample_session_state_dict())

    assert state.session_id == "sess-1"
    assert state.metrics.attack_surface == 3


def test_interpreted_action_rejects_confidence_above_one():
    with pytest.raises(ValidationError):
        InterpretedAction(
            action_summary="Test",
            action_types=["containment"],
            targets=["vpn"],
            intent="Test",
            expected_effects=[],
            risks=[],
            uncertainties=[],
            priority="high",
            confidence=1.2,
        )


def test_interpreted_action_accepts_valid_payload():
    action = InterpretedAction(**sample_interpreted_action_dict())

    assert action.action_types == ["containment"]
    assert action.priority == "high"


def test_interpreted_action_rejects_invalid_action_type():
    payload = sample_interpreted_action_dict()
    payload["action_types"] = ["invalid-action"]

    with pytest.raises(ValidationError):
        InterpretedAction(**payload)


def test_narrator_response_accepts_valid_payload():
    response = NarratorResponse(**sample_narrator_response_dict())

    assert response.injects[0].type == "media"
    assert len(response.key_points) == 2


def test_narrator_response_rejects_too_many_injects():
    with pytest.raises(ValidationError):
        NarratorResponse(
            situation_update="Det här är en tillräckligt lång uppdatering.",
            key_points=["A", "B"],
            new_consequences=[],
            injects=[
                {"type": "media", "title": "A", "message": "Aaa"},
                {"type": "technical", "title": "B", "message": "Bbb"},
                {"type": "operations", "title": "C", "message": "Ccc"},
            ],
            decisions_to_consider=[],
            facilitator_notes="Notering",
        )


def test_narrator_response_rejects_invalid_inject_type():
    payload = sample_narrator_response_dict()
    payload["injects"] = [
        {"type": "invalid", "title": "Xx", "message": "Giltigt meddelande"}
    ]

    with pytest.raises(ValidationError):
        NarratorResponse(**payload)


def test_session_state_validation_requires_non_negative_metrics():
    with pytest.raises(ValidationError):
        SessionState(
            session_id="sess-1",
            scenario_id="scenario-001",
            scenario_version="1.0",
            audience="krisledning",
            current_time="08:15",
            turn_number=0,
            phase="initial-detection",
            metrics=SessionMetrics(
                impact_level=2,
                media_pressure=-1,
                service_disruption=0,
                leadership_pressure=0,
                public_confusion=0,
                attack_surface=3,
            ),
        )


def test_session_state_validation_rejects_empty_session_id():
    payload = sample_session_state_dict()
    payload["session_id"] = ""

    with pytest.raises(ValidationError):
        SessionState(**payload)


def test_turn_validation_accepts_valid_payload():
    turn = Turn(
        turn_number=1,
        participant_input="Vi stänger extern VPN och samlar teamet.",
        interpreted_action=InterpretedAction(**sample_interpreted_action_dict()),
        state_snapshot=SessionState(**sample_session_state_dict()),
        narrator_response=NarratorResponse(**sample_narrator_response_dict()),
    )

    assert turn.turn_number == 1
    assert turn.state_snapshot.session_id == "sess-1"


def test_turn_validation_rejects_turn_number_zero():
    with pytest.raises(ValidationError):
        Turn(
            turn_number=0,
            participant_input="Vi stänger extern VPN och samlar teamet.",
            interpreted_action=InterpretedAction(**sample_interpreted_action_dict()),
            state_snapshot=SessionState(**sample_session_state_dict()),
            narrator_response=NarratorResponse(**sample_narrator_response_dict()),
        )


def test_turn_validation_rejects_short_participant_input():
    with pytest.raises(ValidationError):
        Turn(
            turn_number=1,
            participant_input="Ok",
            interpreted_action=InterpretedAction(**sample_interpreted_action_dict()),
            state_snapshot=SessionState(**sample_session_state_dict()),
            narrator_response=NarratorResponse(**sample_narrator_response_dict()),
        )
