import pytest
from pydantic import ValidationError

from src.models.scenario import Scenario
from src.models.session import SessionMetrics, SessionState
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


def test_scenario_validation_accepts_valid_payload():
    scenario = Scenario(**sample_scenario_dict())
    assert scenario.id == 'scenario-001'
    assert scenario.initial_state.impact_level == 2


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
