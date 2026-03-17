from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.models.scenario import Scenario
from app.models.session import SessionMetrics, SessionState
from app.services.prototype_llm import PrototypeInterpreter, PrototypeNarrator
from app.services.rules_engine import RulesEngine


app = FastAPI(title='Incident Exercise Prototype')

SCENARIOS = {}
SESSIONS = {}


class CreateSessionRequest(BaseModel):
    scenario: Scenario
    audience: str


class TurnRequest(BaseModel):
    participant_input: str


@app.get('/health')
def health() -> dict:
    return {'status': 'ok'}


@app.post('/sessions')
def create_session(request: CreateSessionRequest) -> SessionState:
    scenario = request.scenario
    session_id = f'sess-{len(SESSIONS) + 1}'

    state = SessionState(
        session_id=session_id,
        scenario_id=scenario.id,
        scenario_version=scenario.version,
        audience=request.audience,
        current_time=scenario.initial_state.time,
        turn_number=0,
        phase=scenario.initial_state.phase,
        known_facts=scenario.initial_state.known_facts,
        unknowns=scenario.initial_state.unknowns,
        metrics=SessionMetrics(
            impact_level=scenario.initial_state.impact_level,
            media_pressure=0,
            service_disruption=0,
            leadership_pressure=0,
            public_confusion=0,
            attack_surface=3,
        ),
        focus_items=list(scenario.training_goals),
    )
    SCENARIOS[session_id] = scenario
    SESSIONS[session_id] = state
    return state


@app.post('/sessions/{session_id}/turns')
def post_turn(session_id: str, request: TurnRequest) -> dict:
    state = SESSIONS.get(session_id)
    if not state:
        raise HTTPException(status_code=404, detail='Session not found')

    interpreter = PrototypeInterpreter()
    narrator = PrototypeNarrator()
    engine = RulesEngine()

    interpreted = interpreter.interpret(request.participant_input)
    updated = engine.apply(state, interpreted, request.participant_input)
    response = narrator.narrate(updated)

    SESSIONS[session_id] = updated

    return {
        'interpreted_action': interpreted.model_dump(),
        'session_state': updated.model_dump(),
        'narrator_response': response.model_dump(),
    }
