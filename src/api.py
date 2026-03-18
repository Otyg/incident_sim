# LICENSE HEADER MANAGED BY add-license-header
#
# BSD 3-Clause License
#
# Copyright (c) 2026, Martin Vesterlund
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, this
#    list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
#
# 3. Neither the name of the copyright holder nor the names of its
#    contributors may be used to endorse or promote products derived from
#    this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#

"""FastAPI routes for the incident exercise application.

The module exposes the HTTP entrypoints used by the browser client and tests.
It wires together scenario/session repositories, session bootstrap logic,
timeline retrieval and turn processing through the rules engine and LLM
provider layer.
"""

import json
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from src.logging_utils import configure_logging, get_logger
from src.models.scenario import Audience, Scenario
from src.models.session import SessionMetrics, SessionState
from src.models.turn import Turn
from src.services.llm_provider import (
    LLMProviderError,
    ProviderConfigurationError,
    ProviderOutputValidationError,
    ProviderUpstreamError,
    get_llm_provider,
    validate_interpreted_action,
    validate_narration,
)
from src.services.rules_engine import RulesEngine
from src.storage.factory import create_storage_repositories


configure_logging()
logger = get_logger(__name__)
app = FastAPI(title="Incident Exercise Prototype")
FRONTEND_INDEX = Path(__file__).resolve().parents[1] / "frontend" / "index.html"
SAMPLE_SCENARIO_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "scenarios"
    / "municipality_ransomware.json"
)

scenario_repository, session_repository = create_storage_repositories()
TURN_RETRY_BACKOFF_SECONDS = [2, 4, 8, 16]


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


def build_session_state(
    session_id: str, scenario: Scenario, audience: Audience
) -> SessionState:
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


def load_sample_scenario() -> Scenario:
    """Load the bundled GUI scenario from disk.

    Returns:
        Scenario: Validated sample scenario used for test driving the GUI.
    """

    logger.info("Loading bundled sample scenario from %s", SAMPLE_SCENARIO_PATH)
    with SAMPLE_SCENARIO_PATH.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    return Scenario.model_validate(payload)


@app.get("/health")
async def health() -> dict:
    """Return a simple liveness response for backend health checks.

    Returns:
        dict: Static health payload with status information.
    """

    return {"status": "ok"}


@app.get("/", include_in_schema=False)
async def frontend() -> FileResponse:
    """Serve the static browser client entrypoint.

    Returns:
        FileResponse: The frontend HTML file.

    Raises:
        RuntimeError: Indirectly if the frontend file cannot be read by the
            underlying file response implementation.
    """

    return FileResponse(FRONTEND_INDEX)


@app.get("/sample-scenarios/default", response_model=Scenario)
async def get_default_sample_scenario() -> Scenario:
    """Return the bundled sample scenario used by the browser client.

    Returns:
        Scenario: Default GUI scenario.
    """

    logger.info("Returning default sample scenario")
    return load_sample_scenario()


@app.post("/scenarios", response_model=Scenario)
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

    logger.info("Saving scenario scenario_id=%s", scenario.id)
    return scenario_repository.save(scenario)


@app.get("/scenarios/{scenario_id}", response_model=Scenario)
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
        logger.warning("Scenario not found for scenario_id=%s", scenario_id)
        raise HTTPException(status_code=404, detail="Scenario not found")

    logger.info("Fetched scenario scenario_id=%s", scenario_id)
    return scenario


@app.post("/sessions", response_model=SessionState)
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
        logger.warning(
            "Session creation failed because scenario was missing scenario_id=%s",
            request.scenario_id,
        )
        raise HTTPException(status_code=404, detail="Scenario not found")

    session_id = f"sess-{session_repository.count() + 1}"
    state = build_session_state(session_id, scenario, request.audience)
    logger.info(
        "Creating session session_id=%s scenario_id=%s audience=%s",
        session_id,
        scenario.id,
        request.audience,
    )
    return session_repository.save(state)


@app.get("/sessions/{session_id}", response_model=SessionState)
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
        logger.warning("Session not found for session_id=%s", session_id)
        raise HTTPException(status_code=404, detail="Session not found")

    logger.info(
        "Fetched session session_id=%s turn_number=%s", session_id, state.turn_number
    )
    return state


@app.get("/sessions/{session_id}/timeline", response_model=list[Turn])
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
        logger.warning(
            "Timeline request failed because session was missing session_id=%s",
            session_id,
        )
        raise HTTPException(status_code=404, detail="Session not found")

    timeline = session_repository.get_timeline(session_id)
    logger.info(
        "Fetched timeline session_id=%s turn_count=%s",
        session_id,
        len(timeline),
    )
    return timeline


@app.post("/sessions/{session_id}/turns", response_model=Turn)
async def post_turn(
    session_id: str,
    request: TurnRequest,
    x_retry_attempt: int = Header(default=1, alias="X-Retry-Attempt"),
    x_retry_max_attempts: int = Header(default=5, alias="X-Retry-Max-Attempts"),
) -> Turn | JSONResponse:
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

    attempt = max(1, x_retry_attempt)
    max_attempts = max(1, x_retry_max_attempts)

    try:
        logger.info(
            "Processing turn request session_id=%s participant_input_length=%s attempt=%s max_attempts=%s",
            session_id,
            len(request.participant_input),
            attempt,
            max_attempts,
        )
        state = session_repository.get(session_id)
        if not state:
            logger.warning(
                "Turn request failed because session was missing session_id=%s",
                session_id,
            )
            raise HTTPException(status_code=404, detail="Session not found")

        engine = RulesEngine()
        provider = get_llm_provider()
        logger.info(
            "Using provider=%s for session_id=%s current_turn=%s",
            provider.__class__.__name__,
            session_id,
            state.turn_number,
        )

        interpreted = validate_interpreted_action(
            provider.interpret_action(request.participant_input)
        )
        logger.info(
            "Participant action interpreted session_id=%s action_types=%s priority=%s",
            session_id,
            interpreted.action_types,
            interpreted.priority,
        )

        updated = engine.apply(state, interpreted, request.participant_input)
        logger.info(
            "Rules engine updated state session_id=%s new_turn=%s impact_level=%s media_pressure=%s service_disruption=%s",
            session_id,
            updated.turn_number,
            updated.metrics.impact_level,
            updated.metrics.media_pressure,
            updated.metrics.service_disruption,
        )

        response = validate_narration(provider.generate_narration(updated))
        logger.info(
            "Narration generated session_id=%s key_points=%s inject_count=%s",
            session_id,
            len(response.key_points),
            len(response.injects),
        )

        session_repository.save(updated)
        turn = Turn(
            turn_number=updated.turn_number,
            participant_input=request.participant_input,
            interpreted_action=interpreted,
            state_snapshot=updated,
            narrator_response=response,
        )
        session_repository.append_turn(session_id, turn)
        logger.info(
            "Turn persisted session_id=%s turn_number=%s",
            session_id,
            turn.turn_number,
        )
        return turn
    except HTTPException:
        raise
    except ProviderOutputValidationError as exc:
        logger.warning(
            "Provider output validation failed session_id=%s detail=%s",
            session_id,
            exc,
            exc_info=True,
        )
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ProviderConfigurationError as exc:
        logger.warning(
            "Provider configuration error session_id=%s detail=%s",
            session_id,
            exc,
            exc_info=True,
        )
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except LLMProviderError as exc:
        if isinstance(exc, ProviderUpstreamError):
            retry_after_seconds = None
            if exc.retryable and attempt < max_attempts:
                retry_index = min(attempt - 1, len(TURN_RETRY_BACKOFF_SECONDS) - 1)
                retry_after_seconds = TURN_RETRY_BACKOFF_SECONDS[retry_index]
                logger.warning(
                    "Retryable provider upstream error session_id=%s stage=%s upstream_status=%s attempt=%s max_attempts=%s retry_after_seconds=%s",
                    session_id,
                    exc.provider_stage,
                    exc.upstream_status_code,
                    attempt,
                    max_attempts,
                    retry_after_seconds,
                    exc_info=True,
                )
            else:
                logger.error(
                    "Provider upstream error stopped turn processing session_id=%s stage=%s upstream_status=%s retryable=%s attempt=%s max_attempts=%s",
                    session_id,
                    exc.provider_stage,
                    exc.upstream_status_code,
                    exc.retryable,
                    attempt,
                    max_attempts,
                    exc_info=True,
                )

            return JSONResponse(
                status_code=502,
                content={
                    "detail": str(exc),
                    "error_code": (
                        "llm_provider_retryable_failure"
                        if exc.retryable
                        else "llm_provider_upstream_failure"
                    ),
                    "retryable": exc.retryable,
                    "retry_after_seconds": retry_after_seconds,
                    "attempt": attempt,
                    "max_attempts": max_attempts,
                    "provider_stage": exc.provider_stage,
                    "upstream_status_code": exc.upstream_status_code,
                },
            )

        logger.error(
            "Provider runtime error stopped turn processing session_id=%s detail=%s",
            session_id,
            exc,
            exc_info=True,
        )
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        logger.error(
            "Unhandled blocking error while processing turn session_id=%s",
            session_id,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Internal server error") from exc
