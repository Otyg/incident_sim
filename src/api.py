from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from src.models.scenario import Audience, Scenario
from src.models.session import SessionMetrics, SessionState
from src.models.turn import Turn
from src.services.llm_provider import (
    LLMProviderError,
    ProviderConfigurationError,
    ProviderOutputValidationError,
    get_llm_provider,
    validate_interpreted_action,
    validate_narration,
)
from src.services.rules_engine import RulesEngine
from src.storage.in_memory import InMemoryScenarioRepository, InMemorySessionRepository


app = FastAPI(title='Incident Exercise Prototype')

scenario_repository = InMemoryScenarioRepository()
session_repository = InMemorySessionRepository()


class CreateSessionRequest(BaseModel):
    scenario_id: str = Field(min_length=1)
    audience: Audience


class TurnRequest(BaseModel):
    participant_input: str = Field(min_length=3)


def build_session_state(session_id: str, scenario: Scenario, audience: Audience) -> SessionState:
    return SessionState(
        session_id=session_id,
        scenario_id=scenario.id,
        scenario_version=scenario.version,
        audience=audience,
        current_time=scenario.initial_state.time,
        turn_number=0,
        phase=scenario.initial_state.phase,
        known_facts=list(scenario.initial_state.known_facts),
        unknowns=list(scenario.initial_state.unknowns),
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


@app.get('/health')
async def health() -> dict:
    return {'status': 'ok'}


@app.post('/scenarios', response_model=Scenario)
async def create_scenario(scenario: Scenario) -> Scenario:
    return scenario_repository.save(scenario)


@app.get('/scenarios/{scenario_id}', response_model=Scenario)
async def get_scenario(scenario_id: str) -> Scenario:
    scenario = scenario_repository.get(scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail='Scenario not found')

    return scenario


@app.post('/sessions', response_model=SessionState)
async def create_session(request: CreateSessionRequest) -> SessionState:
    scenario = scenario_repository.get(request.scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail='Scenario not found')

    session_id = f'sess-{session_repository.count() + 1}'
    state = build_session_state(session_id, scenario, request.audience)
    return session_repository.save(state)


@app.get('/sessions/{session_id}', response_model=SessionState)
async def get_session(session_id: str) -> SessionState:
    state = session_repository.get(session_id)
    if not state:
        raise HTTPException(status_code=404, detail='Session not found')

    return state


@app.get('/sessions/{session_id}/timeline', response_model=list[Turn])
async def get_timeline(session_id: str) -> list[Turn]:
    state = session_repository.get(session_id)
    if not state:
        raise HTTPException(status_code=404, detail='Session not found')

    return session_repository.get_timeline(session_id)


@app.post('/sessions/{session_id}/turns', response_model=Turn)
async def post_turn(session_id: str, request: TurnRequest) -> Turn:
    state = session_repository.get(session_id)
    if not state:
        raise HTTPException(status_code=404, detail='Session not found')

    engine = RulesEngine()
    provider = get_llm_provider()

    try:
        interpreted = validate_interpreted_action(provider.interpret_action(request.participant_input))
    except ProviderOutputValidationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ProviderConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except LLMProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    updated = engine.apply(state, interpreted, request.participant_input)

    try:
        response = validate_narration(provider.generate_narration(updated))
    except ProviderOutputValidationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ProviderConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except LLMProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    session_repository.save(updated)
    turn = Turn(
        turn_number=updated.turn_number,
        participant_input=request.participant_input,
        interpreted_action=interpreted,
        state_snapshot=updated,
        narrator_response=response,
    )
    session_repository.append_turn(session_id, turn)
    return turn
