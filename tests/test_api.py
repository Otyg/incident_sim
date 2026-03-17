import asyncio
import json

import pytest

from src import api as api_module
from src.main import app
from tests.mock_llm_provider import MockLLMProvider


def request_json(method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    messages = []
    payload = json.dumps(body).encode() if body is not None else b''
    delivered = False

    async def receive():
        nonlocal delivered
        if not delivered:
            delivered = True
            return {'type': 'http.request', 'body': payload, 'more_body': False}

        return {'type': 'http.disconnect'}

    async def send(message):
        messages.append(message)

    scope = {
        'type': 'http',
        'asgi': {'version': '3.0'},
        'http_version': '1.1',
        'method': method,
        'scheme': 'http',
        'path': path,
        'raw_path': path.encode(),
        'query_string': b'',
        'headers': [(b'content-type', b'application/json')],
        'client': ('127.0.0.1', 12345),
        'server': ('testserver', 80),
        'root_path': '',
    }

    asyncio.run(app(scope, receive, send))

    status = messages[0]['status']
    response_body = messages[1].get('body', b'')
    parsed_body = json.loads(response_body) if response_body else {}
    return status, parsed_body


def sample_scenario_payload():
    return {
        'id': 'scenario-001',
        'title': 'Ransomware mot kommunal verksamhet',
        'version': '1.0',
        'description': 'Testscenario för API-flödet.',
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


def test_create_and_get_scenario():
    scenario = sample_scenario_payload()

    create_status, create_body = request_json('POST', '/scenarios', scenario)
    get_status, get_body = request_json('GET', '/scenarios/scenario-001')

    assert create_status == 200
    assert create_body['id'] == 'scenario-001'
    assert get_status == 200
    assert get_body['title'] == scenario['title']


def test_create_and_get_session_from_existing_scenario():
    scenario = sample_scenario_payload()
    request_json('POST', '/scenarios', scenario)

    create_status, create_body = request_json(
        'POST',
        '/sessions',
        {'scenario_id': 'scenario-001', 'audience': 'krisledning'},
    )
    get_status, get_body = request_json('GET', f"/sessions/{create_body['session_id']}")

    assert create_status == 200
    assert create_body['scenario_id'] == 'scenario-001'
    assert create_body['audience'] == 'krisledning'
    assert get_status == 200
    assert get_body['session_id'] == create_body['session_id']


def test_post_turn_returns_basic_turn_response(monkeypatch):
    monkeypatch.setattr(api_module, 'get_llm_provider', lambda: MockLLMProvider())

    scenario = sample_scenario_payload()
    request_json('POST', '/scenarios', scenario)
    _, session = request_json(
        'POST',
        '/sessions',
        {'scenario_id': 'scenario-001', 'audience': 'krisledning'},
    )

    status, body = request_json(
        'POST',
        f"/sessions/{session['session_id']}/turns",
        {'participant_input': 'Vi stänger extern VPN och samlar incidentledningsgruppen.'},
    )

    assert status == 200
    assert body['turn_number'] == 1
    assert body['participant_input'].startswith('Vi stänger extern VPN')
    assert body['interpreted_action']['priority'] == 'high'
    assert body['state_snapshot']['session_id'] == session['session_id']
    assert body['narrator_response']['key_points']


def test_post_turn_returns_503_for_unavailable_openai_provider(monkeypatch):
    scenario = sample_scenario_payload()
    request_json('POST', '/scenarios', scenario)
    _, session = request_json(
        'POST',
        '/sessions',
        {'scenario_id': 'scenario-001', 'audience': 'krisledning'},
    )
    monkeypatch.setenv('INCIDENT_SIM_LLM_PROVIDER', 'openai')

    status, body = request_json(
        'POST',
        f"/sessions/{session['session_id']}/turns",
        {'participant_input': 'Vi stänger extern VPN.'},
    )

    assert status == 503
    assert 'not implemented yet' in body['detail']


def test_post_turn_returns_502_for_invalid_provider_output(monkeypatch):
    class BadProvider:
        def interpret_action(self, participant_input: str) -> dict:
            return {'action_summary': 'x'}

        def generate_narration(self, state) -> dict:
            return {}

    monkeypatch.setattr(api_module, 'get_llm_provider', lambda: BadProvider())

    scenario = sample_scenario_payload()
    request_json('POST', '/scenarios', scenario)
    _, session = request_json(
        'POST',
        '/sessions',
        {'scenario_id': 'scenario-001', 'audience': 'krisledning'},
    )

    status, body = request_json(
        'POST',
        f"/sessions/{session['session_id']}/turns",
        {'participant_input': 'Vi stänger extern VPN.'},
    )

    assert status == 502
    assert body['detail'] == 'Invalid interpreted action payload'
