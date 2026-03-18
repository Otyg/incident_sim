"""FastAPI routes for the incident exercise application.

The module exposes the HTTP entrypoints used by the browser client and tests.
It wires together scenario/session repositories, session bootstrap logic,
timeline retrieval and turn processing through the rules engine and LLM
provider layer.
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
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
from src.storage.factory import StorageConfigurationError, create_storage_repositories


app = FastAPI(title='Incident Exercise Prototype')
FRONTEND_INDEX = Path(__file__).resolve().parents[1] / 'frontend' / 'index.html'

scenario_repository, session_repository = create_storage_repositories()


class CreateSessionRequest(BaseModel):
    """Request body for starting a new session from an existing scenario.

    Attributes:
        scenario_id: Identifier of the stored scenario to start from.
        audience: Audience profile used when the session state is initialized.
    """

    scenario_id: str = Field(min_length=1)
    audience: Audience


class TurnRequest(BaseModel):
    """Request body for posting a participant action.

    Attributes:
        participant_input: Free-text description of the participant action.
    """

    participant_input: str = Field(min_length=3)


def build_session_state(session_id: str, scenario: Scenario, audience: Audience) -> SessionState:
    """Create the initial session state for a stored scenario.

    Args:
        session_id: Generated identifier for the session.
        scenario: Scenario used as the source for the initial state.
        audience: Audience profile selected for the exercise session.

    Returns:
        SessionState: Initialized session state ready to be saved.
    """

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
    """Return a simple liveness response for backend health checks.

    Returns:
        dict: Static health payload with status information.
    """

    return {'status': 'ok'}


@app.get('/', include_in_schema=False)
async def frontend() -> FileResponse:
    """Serve the static browser client entrypoint.

    Returns:
        FileResponse: The frontend HTML file.

    Raises:
        RuntimeError: Indirectly if the frontend file cannot be read by the
            underlying file response implementation.
    """

    return FileResponse(FRONTEND_INDEX)


@app.post('/scenarios', response_model=Scenario)
async def create_scenario(scenario: Scenario) -> Scenario:
    """Store a scenario in the in-memory repository.

    Args:
        scenario: Validated scenario payload to persist.

    Returns:
        Scenario: The stored scenario.

    Raises:
        StorageConfigurationError: Indirectly during module initialization if
            repository configuration is invalid.
    """

    return scenario_repository.save(scenario)


@app.get('/scenarios/{scenario_id}', response_model=Scenario)
async def get_scenario(scenario_id: str) -> Scenario:
    """Fetch a stored scenario by identifier.

    Args:
        scenario_id: Identifier of the scenario to fetch.

    Returns:
        Scenario: The stored scenario.

    Raises:
        HTTPException: If the scenario does not exist.
    """

    scenario = scenario_repository.get(scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail='Scenario not found')

    return scenario


@app.post('/sessions', response_model=SessionState)
async def create_session(request: CreateSessionRequest) -> SessionState:
    """Start a new session from a stored scenario.

    Args:
        request: Session creation payload containing scenario and audience.

    Returns:
        SessionState: Persisted initial session state.

    Raises:
        HTTPException: If the referenced scenario does not exist.
    """

    scenario = scenario_repository.get(request.scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail='Scenario not found')

    session_id = f'sess-{session_repository.count() + 1}'
    state = build_session_state(session_id, scenario, request.audience)
    return session_repository.save(state)


@app.get('/sessions/{session_id}', response_model=SessionState)
async def get_session(session_id: str) -> SessionState:
    """Fetch the latest stored state for a session.

    Args:
        session_id: Identifier of the session to fetch.

    Returns:
        SessionState: Latest persisted session state.

    Raises:
        HTTPException: If the session does not exist.
    """

    state = session_repository.get(session_id)
    if not state:
        raise HTTPException(status_code=404, detail='Session not found')

    return state


@app.get('/sessions/{session_id}/timeline', response_model=list[Turn])
async def get_timeline(session_id: str) -> list[Turn]:
    """Return the stored turn timeline for a session.

    Args:
        session_id: Identifier of the session whose timeline should be read.

    Returns:
        list[Turn]: Stored turns in insertion order.

    Raises:
        HTTPException: If the session does not exist.
    """

    state = session_repository.get(session_id)
    if not state:
        raise HTTPException(status_code=404, detail='Session not found')

    return session_repository.get_timeline(session_id)


@app.post('/sessions/{session_id}/turns', response_model=Turn)
async def post_turn(session_id: str, request: TurnRequest) -> Turn:
    """Process a participant action and append it to the session timeline.

    Args:
        session_id: Identifier of the session to update.
        request: Turn payload containing the participant action text.

    Returns:
        Turn: Persisted turn containing interpreted action, state snapshot and
            generated narration.

    Raises:
        HTTPException: If the session is missing, provider output is invalid,
            or the selected provider is unavailable.
    """

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
