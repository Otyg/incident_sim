from src.models.scenario import Scenario
from src.models.session import SessionFlags, SessionMetrics, SessionState
from src.schemas.interpreted_action import InterpretedAction
from src.services.scenario_engine import ScenarioEngine


def make_scenario(executable_rules: list[dict]) -> Scenario:
    return Scenario.model_validate(
        {
            "id": "scenario-engine-001",
            "title": "Scenario Engine Test",
            "version": "1.0",
            "description": "Scenario for datadriven scenariomotor.",
            "audiences": ["krisledning"],
            "training_goals": ["Öva state transitions"],
            "difficulty": "medium",
            "timebox_minutes": 60,
            "background": {
                "organization_type": "kommun",
                "context": "Testkontext",
                "threat_actor": "okänd",
                "assumptions": [],
            },
            "states": [
                {
                    "id": "state-initial-detection",
                    "phase": "initial-detection",
                    "title": "Initial detection",
                    "description": "Det första state-läget för scenario engine-testet.",
                    "time": "08:15",
                    "impact_level": 3,
                    "narration": {
                        "default": {
                            "situation_update": "Scenario engine-testet startar i ett tidigt detektionsläge.",
                            "key_points": [
                                "Regelutvärdering ska kunna ske från start.",
                                "State transition ska vara deterministisk.",
                            ],
                            "new_consequences": [],
                            "injects": [],
                            "decisions_to_consider": ["Vilken regel ska slå först?"],
                            "facilitator_notes": "Fördefinierat startnarrativ för scenario engine-test.",
                        }
                    },
                },
                {
                    "id": "state-containment",
                    "phase": "containment",
                    "title": "Containment",
                    "description": "Containment-läget för scenario engine-testet.",
                },
            ],
            "actors": [],
            "inject_catalog": [],
            "rules": [],
            "executable_rules": executable_rules,
            "presentation_guidelines": {
                "krisledning": {"focus": ["beslut"], "tone": "strategisk"}
            },
        }
    )


def make_state() -> SessionState:
    return SessionState(
        session_id="sess-1",
        scenario_id="scenario-engine-001",
        scenario_version="1.0",
        audience="krisledning",
        current_time="08:15",
        turn_number=1,
        phase="initial-detection",
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


def make_action(action_types: list[str], targets: list[str]) -> InterpretedAction:
    return InterpretedAction(
        action_summary="Test action",
        action_types=action_types,
        targets=targets,
        intent="Test intent",
        expected_effects=[],
        risks=[],
        uncertainties=[],
        priority="high",
        confidence=0.8,
    )


def test_scenario_engine_triggers_contains_rule_on_action_type():
    scenario = make_scenario(
        [
            {
                "id": "rule-containment-phase",
                "name": "Containment byter fas",
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
            }
        ]
    )

    updated = ScenarioEngine().apply(
        scenario,
        make_state(),
        "turn_processed",
        make_action(["containment"], ["vpn"]),
    )

    assert updated.phase == "containment"


def test_scenario_engine_triggers_metric_threshold_rule():
    scenario = make_scenario(
        [
            {
                "id": "rule-ops-inject",
                "name": "Operations inject",
                "trigger": "turn_processed",
                "conditions": [
                    {
                        "fact": "state.metrics.service_disruption",
                        "operator": "gte",
                        "value": 2,
                    }
                ],
                "effects": [
                    {"type": "add_active_inject", "inject_id": "inject-ops-001"}
                ],
                "priority": "medium",
            }
        ]
    )
    state = make_state()
    state.metrics.service_disruption = 2

    updated = ScenarioEngine().apply(
        scenario,
        state,
        "turn_processed",
        make_action(["coordination"], []),
    )

    assert "inject-ops-001" in updated.active_injects


def test_scenario_engine_once_rule_only_applies_once():
    scenario = make_scenario(
        [
            {
                "id": "rule-media-inject",
                "name": "Media inject",
                "trigger": "turn_processed",
                "conditions": [
                    {
                        "fact": "state.metrics.media_pressure",
                        "operator": "gte",
                        "value": 2,
                    }
                ],
                "effects": [
                    {"type": "add_active_inject", "inject_id": "inject-media-001"}
                ],
                "priority": "medium",
                "once": True,
            }
        ]
    )
    state = make_state()
    state.metrics.media_pressure = 2

    first = ScenarioEngine().apply(
        scenario,
        state,
        "turn_processed",
        make_action(["coordination"], []),
    )
    second = ScenarioEngine().apply(
        scenario,
        first,
        "turn_processed",
        make_action(["coordination"], []),
    )

    assert first.active_injects == ["inject-media-001"]
    assert second.active_injects == ["inject-media-001"]
    assert (
        sum(1 for item in second.exercise_log if item.text == "rule-media-inject") == 1
    )


def test_scenario_engine_applies_multiple_rules_in_priority_order():
    scenario = make_scenario(
        [
            {
                "id": "rule-medium",
                "name": "Medium priority",
                "trigger": "turn_processed",
                "conditions": [],
                "effects": [
                    {
                        "type": "append_exercise_log",
                        "log_type": "scenario_event",
                        "message": "medium",
                    }
                ],
                "priority": "medium",
            },
            {
                "id": "rule-high",
                "name": "High priority",
                "trigger": "turn_processed",
                "conditions": [],
                "effects": [
                    {
                        "type": "append_exercise_log",
                        "log_type": "scenario_event",
                        "message": "high",
                    }
                ],
                "priority": "high",
            },
        ]
    )

    updated = ScenarioEngine().apply(
        scenario,
        make_state(),
        "turn_processed",
        make_action(["monitoring"], []),
    )

    scenario_events = [
        item.text for item in updated.exercise_log if item.type == "scenario_event"
    ]

    assert scenario_events[:2] == ["high", "medium"]
