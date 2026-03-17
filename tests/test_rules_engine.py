from src.models.session import SessionFlags, SessionMetrics, SessionState
from src.schemas.interpreted_action import InterpretedAction
from src.services.rules_engine import RulesEngine


def make_state() -> SessionState:
    return SessionState(
        session_id='sess-1',
        scenario_id='scenario-001',
        scenario_version='1.0',
        audience='krisledning',
        current_time='08:15',
        turn_number=0,
        phase='initial-detection',
        known_facts=['Inloggningsproblem'],
        unknowns=['Omfattning oklar'],
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


def test_rules_engine_updates_containment_effects():
    state = make_state()
    action = InterpretedAction(
        action_summary='Stänger extern VPN.',
        action_types=['containment'],
        targets=['vpn', 'external_access'],
        intent='Minska attackyta',
        expected_effects=[],
        risks=[],
        uncertainties=[],
        priority='high',
        confidence=0.9,
    )

    updated = RulesEngine().apply(state, action, 'Vi stänger extern VPN.')

    assert updated.turn_number == 1
    assert updated.metrics.attack_surface == 2
    assert updated.metrics.service_disruption == 2
    assert updated.flags.external_access_restricted is True
    assert 'inject-ops-001' in updated.active_injects


def test_rules_engine_increases_media_pressure_after_missing_communication_twice():
    state = make_state()
    state.no_communication_turns = 1
    action = InterpretedAction(
        action_summary='Samlar teamet.',
        action_types=['coordination'],
        targets=['incident_management_team'],
        intent='Samordna arbetet',
        expected_effects=[],
        risks=[],
        uncertainties=[],
        priority='high',
        confidence=0.9,
    )

    updated = RulesEngine().apply(state, action, 'Vi samlar teamet.')

    assert updated.no_communication_turns == 2
    assert updated.metrics.media_pressure == 2
    assert 'inject-media-001' in updated.active_injects


def test_rules_engine_resets_no_communication_counter_when_communication_occurs():
    state = make_state()
    state.no_communication_turns = 2
    action = InterpretedAction(
        action_summary='Vi går ut med ett första uttalande.',
        action_types=['communication'],
        targets=['media'],
        intent='Minska osäkerhet',
        expected_effects=[],
        risks=[],
        uncertainties=[],
        priority='high',
        confidence=0.95,
    )

    updated = RulesEngine().apply(state, action, 'Vi går ut med ett första uttalande.')

    assert updated.no_communication_turns == 0
    assert updated.flags.external_comms_sent is True
