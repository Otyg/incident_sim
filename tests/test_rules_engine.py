import pytest

from src.models.scenario import Scenario
from src.models.session import SessionFlags, SessionMetrics, SessionState
from src.schemas.interpreted_action import InterpretedAction
from src.services.rules_engine import RulesEngine


def make_legacy_scenario() -> Scenario:
    return Scenario.model_validate(
        {
            "id": "scenario-001",
            "title": "Testscenario",
            "version": "1.0",
            "description": "Scenario for rules engine tests.",
            "audiences": ["krisledning"],
            "training_goals": ["Öva prioritering"],
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
                    "description": "Det första state-läget för rules engine-testet.",
                    "time": "08:15",
                    "impact_level": 3,
                    "narration": {
                        "default": {
                            "situation_update": "Testscenariot startar i ett osäkert men hanterbart läge.",
                            "key_points": [
                                "Flera symptom behöver följas upp.",
                                "Deltagarna behöver snabbt skapa lägesbild.",
                            ],
                            "new_consequences": [],
                            "injects": [],
                            "decisions_to_consider": [
                                "Vilken åtgärd ska prioriteras först?"
                            ],
                            "facilitator_notes": "Fördefinierat startnarrativ för testscenario.",
                        }
                    },
                },
                {
                    "id": "state-containment",
                    "phase": "containment",
                    "title": "Containment",
                    "description": "Containment-läget för rules engine-testet.",
                },
            ],
            "actors": [],
            "inject_catalog": [],
            "rules": [],
            "executable_rules": [],
            "presentation_guidelines": {
                "krisledning": {"focus": ["beslut"], "tone": "strategisk"}
            },
        }
    )


def make_datadriven_scenario() -> Scenario:
    payload = make_legacy_scenario().model_dump(exclude_none=True)
    payload["executable_rules"] = [
        {
            "id": "rule-activate-ops-inject",
            "name": "Aktivera operations-inject",
            "trigger": "turn_processed",
            "conditions": [
                {
                    "fact": "state.metrics.service_disruption",
                    "operator": "gte",
                    "value": 2,
                }
            ],
            "effects": [{"type": "add_active_inject", "inject_id": "inject-ops-001"}],
            "priority": "high",
            "once": True,
        },
        {
            "id": "rule-phase-containment",
            "name": "Byt till containment",
            "trigger": "turn_processed",
            "conditions": [
                {
                    "fact": "state.flags.external_access_restricted",
                    "operator": "equals",
                    "value": True,
                },
                {
                    "fact": "state.phase",
                    "operator": "equals",
                    "value": "initial-detection",
                },
            ],
            "effects": [{"type": "set_phase", "phase": "containment"}],
            "priority": "medium",
            "once": True,
        },
        {
            "id": "rule-activate-media-inject",
            "name": "Aktivera media-inject",
            "trigger": "turn_processed",
            "conditions": [
                {
                    "fact": "state.metrics.media_pressure",
                    "operator": "gte",
                    "value": 2,
                }
            ],
            "effects": [{"type": "add_active_inject", "inject_id": "inject-media-001"}],
            "priority": "medium",
            "once": True,
        },
    ]
    return Scenario.model_validate(payload)


def make_state() -> SessionState:
    return SessionState(
        session_id="sess-1",
        scenario_id="scenario-001",
        scenario_version="1.0",
        audience="krisledning",
        current_time="08:15",
        turn_number=0,
        phase="initial-detection",
        known_facts=["Inloggningsproblem"],
        unknowns=["Omfattning oklar"],
        metrics=SessionMetrics(
            impact_level=3,
            media_pressure=1,
            service_disruption=1,
            leadership_pressure=0,
            public_confusion=0,
            attack_surface=3,
        ),
        flags=SessionFlags(),
    )


def make_action(
    action_types: list[str], targets: list[str], summary: str
) -> InterpretedAction:
    return InterpretedAction(
        action_summary=summary,
        action_types=action_types,
        targets=targets,
        intent="Testa state transition.",
        expected_effects=[],
        risks=[],
        uncertainties=[],
        priority="high",
        confidence=0.9,
    )


@pytest.mark.parametrize(
    ("action", "raw_input", "expected_focus_item"),
    [
        (
            make_action(
                ["containment"], ["vpn", "external_access"], "Stänger extern VPN."
            ),
            "Vi stänger extern VPN.",
            "Hantera påverkan på externa tjänster.",
        ),
        (
            make_action(
                ["communication"], ["media"], "Vi går ut med ett första uttalande."
            ),
            "Vi går ut med ett första uttalande.",
            "Samordna fortsatt extern kommunikation.",
        ),
        (
            make_action(
                ["escalation"], ["executive_team"], "Eskalerar till ledningen."
            ),
            "Vi eskalerar till ledningen.",
            "Förbered ledningsbeslut och eskalering.",
        ),
    ],
)
def test_rules_engine_updates_focus_items_for_core_rules(
    action, raw_input, expected_focus_item
):
    updated = RulesEngine().apply(
        make_legacy_scenario(), make_state(), action, raw_input
    )

    assert expected_focus_item in updated.focus_items


def test_rules_engine_updates_containment_effects():
    updated = RulesEngine().apply(
        make_datadriven_scenario(),
        make_state(),
        make_action(["containment"], ["vpn", "external_access"], "Stänger extern VPN."),
        "Vi stänger extern VPN.",
    )

    assert updated.turn_number == 1
    assert updated.current_time == "08:30"
    assert updated.metrics.attack_surface == 2
    assert updated.metrics.service_disruption == 2
    assert updated.flags.external_access_restricted is True
    assert "inject-ops-001" in updated.active_injects
    assert updated.phase == "containment"
    assert (
        "Begränsad extern åtkomst minskar attackytan men påverkar externa tjänster."
        in updated.consequences
    )


@pytest.mark.parametrize(
    (
        "starting_turns",
        "expected_media_pressure",
        "expected_public_confusion",
        "expect_media_inject",
    ),
    [
        (0, 1, 0, False),
        (1, 2, 1, True),
    ],
)
def test_rules_engine_handles_missing_communication_deterministically(
    starting_turns,
    expected_media_pressure,
    expected_public_confusion,
    expect_media_inject,
):
    state = make_state()
    state.no_communication_turns = starting_turns

    updated = RulesEngine().apply(
        make_datadriven_scenario(),
        state,
        make_action(["coordination"], ["incident_management_team"], "Samlar teamet."),
        "Vi samlar teamet.",
    )

    assert updated.no_communication_turns == starting_turns + 1
    assert updated.metrics.media_pressure == expected_media_pressure
    assert updated.metrics.public_confusion == expected_public_confusion
    assert ("inject-media-001" in updated.active_injects) is expect_media_inject


def test_rules_engine_resets_no_communication_counter_when_communication_occurs():
    state = make_state()
    state.no_communication_turns = 2

    updated = RulesEngine().apply(
        make_legacy_scenario(),
        state,
        make_action(
            ["communication"], ["media"], "Vi går ut med ett första uttalande."
        ),
        "Vi går ut med ett första uttalande.",
    )

    assert updated.no_communication_turns == 0
    assert updated.flags.external_comms_sent is True


def test_rules_engine_marks_executive_escalation():
    updated = RulesEngine().apply(
        make_legacy_scenario(),
        make_state(),
        make_action(["escalation"], ["executive_team"], "Eskalerar till ledningen."),
        "Vi eskalerar till ledningen.",
    )

    assert updated.flags.executive_escalation is True


def test_rules_engine_advances_session_time_each_turn():
    updated = RulesEngine().apply(
        make_legacy_scenario(),
        make_state(),
        make_action(["monitoring"], [], "Följer upp läget."),
        "Vi följer upp läget.",
    )

    assert updated.current_time == "08:30"
