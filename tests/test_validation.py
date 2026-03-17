import pytest
from pydantic import ValidationError

from src.models.scenario import Scenario
from src.models.session import SessionMetrics, SessionState
from src.models.turn import Turn
from src.schemas.interpreted_action import InterpretedAction
from src.schemas.narrator_response import NarratorResponse


def sample_scenario_dict():
    return {
        'id': 'scenario-001',
        'title': 'Ransomware mot kommunal verksamhet',
        'version': '1.0',
        'description': 'Testscenario',
        'audiences': ['krisledning', 'it-ledning'],
        'training_goals': ['Öva initial lägesuppfattning'],
        'difficulty': 'medium',
        'timebox_minutes': 90,
        'background': {
            'organization_type': 'kommun',
            'context': 'Testkontext',
            'threat_actor': 'okänd angripare',
            'assumptions': [],
        },
        'initial_state': {
            'time': '08:15',
            'phase': 'initial-detection',
            'known_facts': ['Inloggningsproblem'],
            'unknowns': ['Omfattning oklar'],
            'affected_systems': ['AD'],
            'business_impact': ['Intern påverkan'],
            'impact_level': 2,
        },
        'actors': [],
        'inject_catalog': [],
        'rules': [],
        'presentation_guidelines': {
            'krisledning': {'focus': ['beslut'], 'tone': 'strategisk'},
            'it-ledning': {'focus': ['system'], 'tone': 'operativ'},
        },
    }


def sample_session_state_dict():
    return {
        'session_id': 'sess-1',
        'scenario_id': 'scenario-001',
        'scenario_version': '1.0',
        'audience': 'krisledning',
        'current_time': '08:15',
        'turn_number': 0,
        'phase': 'initial-detection',
        'known_facts': ['Inloggningsproblem'],
        'unknowns': ['Omfattning oklar'],
        'metrics': {
            'impact_level': 2,
            'media_pressure': 0,
            'service_disruption': 0,
            'leadership_pressure': 0,
            'public_confusion': 0,
            'attack_surface': 3,
        },
    }


def sample_interpreted_action_dict():
    return {
        'action_summary': 'Stänger extern VPN.',
        'action_types': ['containment'],
        'targets': ['vpn'],
        'intent': 'Minska attackytan.',
        'expected_effects': ['Minskar extern exponering.'],
        'risks': ['Kan påverka användare.'],
        'uncertainties': ['Om angriparen redan har annan åtkomst.'],
        'priority': 'high',
        'confidence': 0.9,
    }


def sample_narrator_response_dict():
    return {
        'situation_update': 'Läget är fortsatt osäkert men under närmare kontroll efter de första åtgärderna.',
        'key_points': ['Attackytan minskar.', 'Kommunikationsbehovet ökar.'],
        'new_consequences': ['Fjärranvändare påverkas.'],
        'injects': [
            {'type': 'media', 'title': 'Mediefråga', 'message': 'Journalister vill ha en kommentar.'}
        ],
        'decisions_to_consider': ['Behöver vi gå ut externt nu?'],
        'facilitator_notes': 'Använd responsen för fortsatt diskussion.',
    }


def test_scenario_validation_accepts_valid_payload():
    scenario = Scenario(**sample_scenario_dict())
    assert scenario.id == 'scenario-001'
    assert scenario.initial_state.impact_level == 2


def test_scenario_validation_rejects_empty_audiences():
    payload = sample_scenario_dict()
    payload['audiences'] = []

    with pytest.raises(ValidationError):
        Scenario(**payload)


def test_scenario_validation_rejects_timebox_above_limit():
    payload = sample_scenario_dict()
    payload['timebox_minutes'] = 600

    with pytest.raises(ValidationError):
        Scenario(**payload)


def test_session_state_validation_accepts_valid_payload():
    state = SessionState(**sample_session_state_dict())

    assert state.session_id == 'sess-1'
    assert state.metrics.attack_surface == 3


def test_interpreted_action_rejects_confidence_above_one():
    with pytest.raises(ValidationError):
        InterpretedAction(
            action_summary='Test',
            action_types=['containment'],
            targets=['vpn'],
            intent='Test',
            expected_effects=[],
            risks=[],
            uncertainties=[],
            priority='high',
            confidence=1.2,
        )


def test_interpreted_action_accepts_valid_payload():
    action = InterpretedAction(**sample_interpreted_action_dict())

    assert action.action_types == ['containment']
    assert action.priority == 'high'


def test_interpreted_action_rejects_invalid_action_type():
    payload = sample_interpreted_action_dict()
    payload['action_types'] = ['invalid-action']

    with pytest.raises(ValidationError):
        InterpretedAction(**payload)


def test_narrator_response_accepts_valid_payload():
    response = NarratorResponse(**sample_narrator_response_dict())

    assert response.injects[0].type == 'media'
    assert len(response.key_points) == 2


def test_narrator_response_rejects_too_many_injects():
    with pytest.raises(ValidationError):
        NarratorResponse(
            situation_update='Det här är en tillräckligt lång uppdatering.',
            key_points=['A', 'B'],
            new_consequences=[],
            injects=[
                {'type': 'media', 'title': 'A', 'message': 'Aaa'},
                {'type': 'technical', 'title': 'B', 'message': 'Bbb'},
                {'type': 'operations', 'title': 'C', 'message': 'Ccc'},
            ],
            decisions_to_consider=[],
            facilitator_notes='Notering',
        )


def test_narrator_response_rejects_invalid_inject_type():
    payload = sample_narrator_response_dict()
    payload['injects'] = [{'type': 'invalid', 'title': 'Xx', 'message': 'Giltigt meddelande'}]

    with pytest.raises(ValidationError):
        NarratorResponse(**payload)


def test_session_state_validation_requires_non_negative_metrics():
    with pytest.raises(ValidationError):
        SessionState(
            session_id='sess-1',
            scenario_id='scenario-001',
            scenario_version='1.0',
            audience='krisledning',
            current_time='08:15',
            turn_number=0,
            phase='initial-detection',
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
    payload['session_id'] = ''

    with pytest.raises(ValidationError):
        SessionState(**payload)


def test_turn_validation_accepts_valid_payload():
    turn = Turn(
        turn_number=1,
        participant_input='Vi stänger extern VPN och samlar teamet.',
        interpreted_action=InterpretedAction(**sample_interpreted_action_dict()),
        state_snapshot=SessionState(**sample_session_state_dict()),
        narrator_response=NarratorResponse(**sample_narrator_response_dict()),
    )

    assert turn.turn_number == 1
    assert turn.state_snapshot.session_id == 'sess-1'


def test_turn_validation_rejects_turn_number_zero():
    with pytest.raises(ValidationError):
        Turn(
            turn_number=0,
            participant_input='Vi stänger extern VPN och samlar teamet.',
            interpreted_action=InterpretedAction(**sample_interpreted_action_dict()),
            state_snapshot=SessionState(**sample_session_state_dict()),
            narrator_response=NarratorResponse(**sample_narrator_response_dict()),
        )


def test_turn_validation_rejects_short_participant_input():
    with pytest.raises(ValidationError):
        Turn(
            turn_number=1,
            participant_input='Ok',
            interpreted_action=InterpretedAction(**sample_interpreted_action_dict()),
            state_snapshot=SessionState(**sample_session_state_dict()),
            narrator_response=NarratorResponse(**sample_narrator_response_dict()),
        )
