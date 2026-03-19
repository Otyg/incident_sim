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

from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError

from src.logging_utils import configure_logging, get_logger
from src.models.scenario import Audience, Scenario
from src.models.session import ExerciseLogItem, SessionMetrics, SessionState
from src.models.turn import Turn
from src.schemas.debrief_response import DebriefResponse
from src.schemas.narrator_response import NarratorResponse
from src.services.llm_provider import (
    LLMProviderError,
    ProviderConfigurationError,
    ProviderOutputValidationError,
    ProviderResponseFormatError,
    ProviderUpstreamError,
    get_llm_provider,
    validate_debrief,
    validate_interpreted_action,
    validate_narration,
    validate_scenario,
)
from src.services.scenario_action_enricher import ScenarioActionEnricher
from src.services.rules_engine import RulesEngine
from src.services.scenario_engine import ScenarioEngine
from src.storage.factory import create_storage_repositories


configure_logging()
logger = get_logger(__name__)
app = FastAPI(title="Incident Exercise Prototype")
FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"
FRONTEND_INDEX = FRONTEND_DIR / "index.html"
FRONTEND_SETUP = FRONTEND_DIR / "setup.html"
FRONTEND_AUTHORING = FRONTEND_DIR / "authoring.html"
FRONTEND_SESSION = FRONTEND_DIR / "session.html"
FRONTEND_REPORT = FRONTEND_DIR / "report.html"
SAMPLE_SCENARIO_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "scenarios"
    / "municipality_ransomware.json"
)

scenario_repository, session_repository = create_storage_repositories()
TURN_RETRY_BACKOFF_SECONDS = [2, 4, 8, 16]
scenario_engine = ScenarioEngine()
action_enricher = ScenarioActionEnricher()

app.mount("/frontend", StaticFiles(directory=FRONTEND_DIR), name="frontend")


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


class ManualPhaseChangeRequest(BaseModel):
    """Request body for manually changing the active scenario phase."""

    phase: str = Field(min_length=2)


class ManualInjectTriggerRequest(BaseModel):
    """Request body for manually triggering an inject in the active session."""

    inject_id: str = Field(min_length=2)


class CreateSessionResponse(BaseModel):
    """Response body for session creation plus initial narration."""

    session_state: SessionState
    initial_narration: NarratorResponse


class PhaseChangeResponse(BaseModel):
    """Response body for manual phase change plus refreshed narration."""

    session_state: SessionState
    narration: NarratorResponse


class CompleteSessionResponse(BaseModel):
    """Response body for session completion and debrief material."""

    session_state: SessionState
    debrief: DebriefResponse


class ScenarioDraftFromTextRequest(BaseModel):
    """Request body for generating a scenario draft from free-text source."""

    source_text: str = Field(min_length=20)
    source_format: str = Field(default="markdown", min_length=2)


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

    initial_state = scenario.states[0]

    return SessionState(
        session_id=session_id,
        scenario_id=scenario.id,
        scenario_version=scenario.version,
        audience=audience,
        current_time=initial_state.time or "00:00",
        turn_number=0,
        phase=initial_state.phase,
        known_facts=list(initial_state.known_facts or []),
        unknowns=list(initial_state.unknowns or []),
        affected_systems=list(initial_state.affected_systems or []),
        business_impact=list(initial_state.business_impact or []),
        metrics=SessionMetrics(
            impact_level=initial_state.impact_level or 1,
            media_pressure=0,
            service_disruption=0,
            leadership_pressure=0,
            public_confusion=0,
            attack_surface=3,
        ),
        focus_items=list(scenario.training_goals),
    )


def resolve_state_narration(
    state_definition: "ScenarioStateDefinition", audience: Audience
) -> NarratorResponse:
    """Resolve scenario-authored narration for a specific state and audience."""

    configured = state_definition.narration
    if configured is None:
        raise ValueError(f"Scenario state {state_definition.id} is missing narration")

    audience_specific = configured.by_audience.get(audience)
    if audience_specific:
        return audience_specific

    if configured.default:
        return configured.default

    raise ValueError(
        f"Scenario state {state_definition.id} is missing narration for audience {audience}"
    )


def resolve_initial_narration(
    scenario: Scenario, audience: Audience
) -> NarratorResponse:
    """Resolve the scenario-authored initial narration for the selected audience."""

    return resolve_state_narration(scenario.states[0], audience)


def build_phase_narration(
    state: SessionState, target_state: "ScenarioStateDefinition"
) -> NarratorResponse:
    """Build a narration snapshot for a manual phase change."""

    if target_state.narration is not None:
        return validate_narration(
            resolve_state_narration(target_state, state.audience).model_dump()
        )

    provider = get_llm_provider()
    return validate_narration(provider.generate_narration(state))


def load_sample_scenario() -> Scenario:
    """Load the bundled GUI scenario from disk.

    Returns:
        Scenario: Validated sample scenario used for test driving the GUI.
    """

    logger.info("Loading bundled sample scenario from %s", SAMPLE_SCENARIO_PATH)
    with SAMPLE_SCENARIO_PATH.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    return Scenario.model_validate(payload)


async def read_uploaded_scenario(upload: UploadFile) -> Scenario:
    """Read and validate an uploaded scenario JSON file.

    Args:
        upload: Uploaded file expected to contain a complete scenario document.

    Returns:
        Scenario: Validated scenario parsed from the uploaded JSON payload.

    Raises:
        HTTPException: If the file is not UTF-8 JSON or does not validate as a
            scenario.
    """

    try:
        payload = json.loads((await upload.read()).decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=400,
            detail="Uploaded file must be UTF-8 encoded JSON",
        ) from exc
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=400,
            detail="Uploaded file did not contain valid JSON",
        ) from exc

    try:
        return Scenario.model_validate(payload)
    except ValidationError as exc:
        logger.warning(
            "Uploaded scenario JSON failed validation filename=%s",
            upload.filename,
            exc_info=True,
        )
        raise HTTPException(
            status_code=400,
            detail=f"Uploaded scenario was invalid: {exc}",
        ) from exc


@app.get("/health")
async def health() -> dict:
    """Return a simple liveness response for backend health checks.

    Returns:
        dict: Static health payload with status information.
    """

    return {"status": "ok"}


@app.get("/", include_in_schema=False)
async def frontend() -> RedirectResponse:
    """Redirect the browser client root to the setup page.

    Returns:
        RedirectResponse: Redirect to the frontend setup page.
    """

    return RedirectResponse(url="/setup", status_code=307)


@app.get("/setup", include_in_schema=False)
async def frontend_setup() -> FileResponse:
    """Serve the scenario setup page for the browser client."""

    return FileResponse(FRONTEND_SETUP)


@app.get("/authoring", include_in_schema=False)
async def frontend_authoring() -> FileResponse:
    """Serve the scenario authoring page for the browser client."""

    return FileResponse(FRONTEND_AUTHORING)


@app.get("/session", include_in_schema=False)
async def frontend_session() -> FileResponse:
    """Serve the active session page for the browser client."""

    return FileResponse(FRONTEND_SESSION)


@app.get("/report", include_in_schema=False)
async def frontend_report() -> FileResponse:
    """Serve the printable report page for completed sessions."""

    return FileResponse(FRONTEND_REPORT)


@app.get(
    "/sample-scenarios/default",
    response_model=Scenario,
    response_model_exclude_none=True,
)
async def get_default_sample_scenario() -> Scenario:
    """Return the bundled sample scenario used by the browser client.

    Returns:
        Scenario: Default GUI scenario.
    """

    logger.info("Returning default sample scenario")
    return load_sample_scenario()


@app.post("/scenarios", response_model=Scenario, response_model_exclude_none=True)
async def create_scenario(scenario: Scenario) -> Scenario:
    """Store a scenario in the configured scenario repository.

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


@app.post(
    "/scenarios/draft-from-text",
    response_model=Scenario,
    response_model_exclude_none=True,
)
async def create_scenario_draft_from_text(
    request: ScenarioDraftFromTextRequest,
) -> Scenario:
    """Generate but do not persist a scenario draft from source text."""

    try:
        provider = get_llm_provider()
        logger.info(
            "Generating scenario draft source_format=%s source_length=%s provider=%s",
            request.source_format,
            len(request.source_text),
            provider.__class__.__name__,
        )
        payload = provider.generate_scenario_draft(
            request.source_text, request.source_format
        )
        if not isinstance(payload, dict):
            raise ProviderOutputValidationError("Invalid scenario payload")

        payload["original_text"] = request.source_text
        scenario = validate_scenario(payload)
        logger.info("Scenario draft generated scenario_id=%s", scenario.id)
        return scenario
    except ProviderOutputValidationError as exc:
        logger.warning(
            "Scenario draft generation validation failed detail=%s",
            exc,
            exc_info=True,
        )
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ProviderConfigurationError as exc:
        logger.warning(
            "Scenario draft generation configuration failed detail=%s",
            exc,
            exc_info=True,
        )
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except LLMProviderError as exc:
        logger.warning(
            "Scenario draft generation provider failure detail=%s",
            exc,
            exc_info=True,
        )
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/scenarios", response_model=list[Scenario], response_model_exclude_none=True)
async def list_scenarios() -> list[Scenario]:
    """List stored scenarios.

    Returns:
        list[Scenario]: All stored scenarios.
    """

    scenarios = scenario_repository.list()
    logger.info("Listed scenarios count=%s", len(scenarios))
    return scenarios


@app.get(
    "/scenarios/{scenario_id}",
    response_model=Scenario,
    response_model_exclude_none=True,
)
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


@app.get("/scenarios/{scenario_id}/download")
async def download_scenario(scenario_id: str) -> Response:
    """Download a stored scenario as a JSON attachment.

    Args:
        scenario_id: Identifier of the scenario to export.

    Returns:
        Response: JSON response with attachment headers for file download.

    Raises:
        HTTPException: If the scenario does not exist.
    """

    scenario = scenario_repository.get(scenario_id)
    if not scenario:
        logger.warning(
            "Scenario download failed because scenario was missing scenario_id=%s",
            scenario_id,
        )
        raise HTTPException(status_code=404, detail="Scenario not found")

    logger.info("Downloading scenario scenario_id=%s", scenario_id)
    return Response(
        content=scenario.model_dump_json(indent=2, exclude_none=True),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{scenario_id}.json"'},
    )


@app.put(
    "/scenarios/{scenario_id}/upload",
    response_model=Scenario,
    response_model_exclude_none=True,
)
async def update_scenario_from_upload(
    scenario_id: str, file: UploadFile = File(...)
) -> Scenario:
    """Replace an existing stored scenario from an uploaded JSON file.

    Args:
        scenario_id: Identifier of the stored scenario to replace.
        file: Uploaded JSON file containing the replacement scenario.

    Returns:
        Scenario: The stored replacement scenario.

    Raises:
        HTTPException: If the scenario does not exist, the upload is invalid or
            the uploaded scenario id does not match ``scenario_id``.
    """

    existing = scenario_repository.get(scenario_id)
    if not existing:
        logger.warning(
            "Scenario upload update failed because scenario was missing scenario_id=%s",
            scenario_id,
        )
        raise HTTPException(status_code=404, detail="Scenario not found")

    scenario = await read_uploaded_scenario(file)
    if scenario.id != scenario_id:
        logger.warning(
            "Scenario upload update rejected due to id mismatch scenario_id=%s uploaded_id=%s",
            scenario_id,
            scenario.id,
        )
        raise HTTPException(
            status_code=400,
            detail=(
                "Uploaded scenario id must match the target scenario id "
                f"({scenario_id})"
            ),
        )

    logger.info(
        "Updating scenario from uploaded file scenario_id=%s filename=%s",
        scenario_id,
        file.filename,
    )
    return scenario_repository.save(scenario)


@app.post("/sessions", response_model=CreateSessionResponse)
async def create_session(request: CreateSessionRequest) -> CreateSessionResponse:
    """Start a new session from a stored scenario.

    Args:
        request: Session creation payload containing scenario and audience.

    Returns:
        CreateSessionResponse: Persisted initial session state together with the
            first narration shown to the facilitator.

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
    state = scenario_engine.apply(
        scenario=scenario,
        state=state,
        trigger="session_started",
    )
    logger.info(
        "Creating session session_id=%s scenario_id=%s audience=%s",
        session_id,
        scenario.id,
        request.audience,
    )

    try:
        initial_narration = validate_narration(
            resolve_initial_narration(scenario, request.audience).model_dump()
        )
        session_repository.save(state)
        logger.info(
            "Session initialized with scenario-authored initial narration session_id=%s audience=%s",
            session_id,
            request.audience,
        )
        return CreateSessionResponse(
            session_state=state,
            initial_narration=initial_narration,
        )
    except (ValueError, ProviderOutputValidationError) as exc:
        logger.error(
            "Scenario initial narration resolution failed session_id=%s detail=%s",
            session_id,
            exc,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=str(exc)) from exc


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


@app.post("/sessions/{session_id}/phase", response_model=PhaseChangeResponse)
async def update_session_phase(
    session_id: str, request: ManualPhaseChangeRequest
) -> PhaseChangeResponse:
    """Manually change the active phase for an ongoing session."""
    try:
        state = session_repository.get(session_id)
        if not state:
            logger.warning(
                "Manual phase change failed because session was missing session_id=%s",
                session_id,
            )
            raise HTTPException(status_code=404, detail="Session not found")

        if state.status != "active":
            logger.warning(
                "Manual phase change rejected because session was not active session_id=%s status=%s",
                session_id,
                state.status,
            )
            raise HTTPException(
                status_code=409,
                detail="Session is not active and phase cannot be changed",
            )

        scenario = scenario_repository.get(state.scenario_id)
        if not scenario:
            logger.error(
                "Manual phase change failed because scenario was missing session_id=%s scenario_id=%s",
                session_id,
                state.scenario_id,
            )
            raise HTTPException(status_code=404, detail="Scenario not found")

        available_phases = scenario_engine.get_defined_phases(scenario)
        if request.phase not in available_phases:
            logger.warning(
                "Manual phase change rejected because phase was not defined session_id=%s phase=%s",
                session_id,
                request.phase,
            )
            raise HTTPException(
                status_code=400,
                detail="Phase is not defined in the scenario",
            )

        target_state = scenario_engine.get_state_definition(scenario, request.phase)
        if target_state is None:
            logger.error(
                "Manual phase change failed because phase definition lookup returned nothing session_id=%s phase=%s",
                session_id,
                request.phase,
            )
            raise HTTPException(
                status_code=400, detail="Phase is not defined in the scenario"
            )

        if request.phase == state.phase:
            logger.info(
                "Manual phase change skipped because phase was already active session_id=%s phase=%s",
                session_id,
                request.phase,
            )
            return PhaseChangeResponse(
                session_state=state,
                narration=build_phase_narration(state, target_state),
            )

        updated = state.model_copy(deep=True)
        previous_phase = updated.phase
        updated = scenario_engine.apply_state_definition(updated, target_state)
        updated.exercise_log.append(
            ExerciseLogItem(
                turn=updated.turn_number,
                type="phase_change",
                text=f"Manuellt fasbyte: {previous_phase} -> {request.phase}",
            )
        )
        narration = build_phase_narration(updated, target_state)
        session_repository.save(updated)
        logger.info(
            "Manual phase change applied session_id=%s from_phase=%s to_phase=%s",
            session_id,
            previous_phase,
            request.phase,
        )
        return PhaseChangeResponse(
            session_state=updated,
            narration=narration,
        )
    except HTTPException:
        raise
    except ProviderOutputValidationError as exc:
        logger.warning(
            "Provider output validation failed during manual phase change session_id=%s detail=%s",
            session_id,
            exc,
            exc_info=True,
        )
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ProviderConfigurationError as exc:
        logger.warning(
            "Provider configuration error during manual phase change session_id=%s detail=%s",
            session_id,
            exc,
            exc_info=True,
        )
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except LLMProviderError as exc:
        logger.error(
            "Provider runtime error during manual phase change session_id=%s detail=%s",
            session_id,
            exc,
            exc_info=True,
        )
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/sessions/{session_id}/injects", response_model=SessionState)
async def trigger_session_inject(
    session_id: str, request: ManualInjectTriggerRequest
) -> SessionState:
    """Manually activate or reactivate an inject for an ongoing session."""

    state = session_repository.get(session_id)
    if not state:
        logger.warning(
            "Manual inject trigger failed because session was missing session_id=%s",
            session_id,
        )
        raise HTTPException(status_code=404, detail="Session not found")

    if state.status != "active":
        logger.warning(
            "Manual inject trigger rejected because session was not active session_id=%s status=%s",
            session_id,
            state.status,
        )
        raise HTTPException(
            status_code=409,
            detail="Session is not active and injects cannot be triggered",
        )

    scenario = scenario_repository.get(state.scenario_id)
    if not scenario:
        logger.error(
            "Manual inject trigger failed because scenario was missing session_id=%s scenario_id=%s",
            session_id,
            state.scenario_id,
        )
        raise HTTPException(status_code=404, detail="Scenario not found")

    inject_definition = next(
        (item for item in scenario.inject_catalog if item.id == request.inject_id),
        None,
    )
    if not inject_definition:
        logger.warning(
            "Manual inject trigger rejected because inject was not defined session_id=%s inject_id=%s",
            session_id,
            request.inject_id,
        )
        raise HTTPException(
            status_code=400,
            detail="Inject is not defined in the scenario",
        )

    if request.inject_id in state.active_injects:
        logger.info(
            "Manual inject trigger skipped because inject was already active session_id=%s inject_id=%s",
            session_id,
            request.inject_id,
        )
        return state

    updated = state.model_copy(deep=True)
    was_resolved = request.inject_id in updated.resolved_injects
    if was_resolved:
        updated.resolved_injects = [
            item for item in updated.resolved_injects if item != request.inject_id
        ]
    updated.active_injects.append(request.inject_id)

    action = "återaktiverat" if was_resolved else "aktiverat"
    updated.exercise_log.append(
        ExerciseLogItem(
            turn=updated.turn_number,
            type="scenario_event",
            text=(
                f"Manuellt inject {action}: "
                f"{inject_definition.title} ({request.inject_id})"
            ),
        )
    )
    session_repository.save(updated)
    logger.info(
        "Manual inject trigger applied session_id=%s inject_id=%s reactivated=%s",
        session_id,
        request.inject_id,
        was_resolved,
    )
    return updated


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


@app.post("/sessions/{session_id}/complete", response_model=CompleteSessionResponse)
async def complete_session(session_id: str) -> CompleteSessionResponse:
    """Mark a session as completed and generate a debrief package."""

    state = session_repository.get(session_id)
    if not state:
        logger.warning(
            "Session completion failed because session was missing session_id=%s",
            session_id,
        )
        raise HTTPException(status_code=404, detail="Session not found")

    timeline = session_repository.get_timeline(session_id)
    if not timeline:
        logger.warning(
            "Session completion failed because timeline was empty session_id=%s",
            session_id,
        )
        raise HTTPException(
            status_code=400,
            detail="Session must contain at least one turn before it can be completed",
        )

    scenario = scenario_repository.get(state.scenario_id)
    if not scenario:
        logger.error(
            "Session completion failed because scenario was missing session_id=%s scenario_id=%s",
            session_id,
            state.scenario_id,
        )
        raise HTTPException(status_code=404, detail="Scenario not found")

    completed_state = state.model_copy(update={"status": "completed"})

    try:
        provider = get_llm_provider()
        logger.info(
            "Generating session debrief session_id=%s provider=%s turn_count=%s",
            session_id,
            provider.__class__.__name__,
            len(timeline),
        )
        debrief = validate_debrief(
            provider.generate_debrief(scenario, completed_state, timeline)
        )
        session_repository.save(completed_state)
        logger.info("Session completed session_id=%s", session_id)
        return CompleteSessionResponse(session_state=completed_state, debrief=debrief)
    except ProviderOutputValidationError as exc:
        logger.warning(
            "Debrief validation failed session_id=%s detail=%s",
            session_id,
            exc,
            exc_info=True,
        )
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ProviderConfigurationError as exc:
        logger.warning(
            "Provider configuration error during session completion session_id=%s detail=%s",
            session_id,
            exc,
            exc_info=True,
        )
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except LLMProviderError as exc:
        logger.error(
            "Provider runtime error during session completion session_id=%s detail=%s",
            session_id,
            exc,
            exc_info=True,
        )
        raise HTTPException(status_code=502, detail=str(exc)) from exc


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
        if state.status != "active":
            logger.warning(
                "Turn request rejected because session was not active session_id=%s status=%s",
                session_id,
                state.status,
            )
            raise HTTPException(
                status_code=409,
                detail="Session is not active and cannot accept additional turns",
            )

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
        scenario = scenario_repository.get(state.scenario_id)
        if not scenario:
            logger.error(
                "Turn request failed because scenario was missing session_id=%s scenario_id=%s",
                session_id,
                state.scenario_id,
            )
            raise HTTPException(status_code=404, detail="Scenario not found")

        logger.info(
            "Participant action interpreted session_id=%s action_types=%s targets=%s priority=%s",
            session_id,
            interpreted.action_types,
            interpreted.targets,
            interpreted.priority,
        )
        enriched = action_enricher.enrich(
            scenario, request.participant_input, interpreted
        )
        if enriched.log_messages:
            logger.info(
                "Participant action enriched session_id=%s action_types=%s targets=%s support=%s",
                session_id,
                enriched.action.action_types,
                enriched.action.targets,
                enriched.log_messages,
            )

        updated = engine.apply(
            scenario,
            state,
            enriched.action,
            request.participant_input,
            interpretation_log_messages=enriched.log_messages,
        )
        activated_state = None
        if updated.phase != state.phase:
            activated_state = scenario_engine.get_state_definition(
                scenario, updated.phase
            )
            if activated_state is not None:
                updated = scenario_engine.apply_state_definition(
                    updated, activated_state
                )
        logger.info(
            "Rules engine updated state session_id=%s new_turn=%s impact_level=%s media_pressure=%s service_disruption=%s",
            session_id,
            updated.turn_number,
            updated.metrics.impact_level,
            updated.metrics.media_pressure,
            updated.metrics.service_disruption,
        )

        if activated_state and scenario_engine.is_full_state_definition(
            activated_state
        ):
            response = validate_narration(
                resolve_state_narration(activated_state, updated.audience).model_dump()
            )
            logger.info(
                "Narration resolved from scenario-authored state session_id=%s state_id=%s phase=%s",
                session_id,
                activated_state.id,
                activated_state.phase,
            )
        else:
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

        if isinstance(exc, ProviderResponseFormatError):
            retry_after_seconds = None
            if exc.retryable and attempt < max_attempts:
                retry_index = min(attempt - 1, len(TURN_RETRY_BACKOFF_SECONDS) - 1)
                retry_after_seconds = TURN_RETRY_BACKOFF_SECONDS[retry_index]
                logger.warning(
                    "Retryable provider response format error session_id=%s stage=%s attempt=%s max_attempts=%s retry_after_seconds=%s raw_excerpt=%s",
                    session_id,
                    exc.provider_stage,
                    attempt,
                    max_attempts,
                    retry_after_seconds,
                    exc.raw_response_excerpt,
                    exc_info=True,
                )
            else:
                logger.error(
                    "Provider response format error stopped turn processing session_id=%s stage=%s retryable=%s attempt=%s max_attempts=%s raw_excerpt=%s",
                    session_id,
                    exc.provider_stage,
                    exc.retryable,
                    attempt,
                    max_attempts,
                    exc.raw_response_excerpt,
                    exc_info=True,
                )

            return JSONResponse(
                status_code=502,
                content={
                    "detail": str(exc),
                    "error_code": (
                        "llm_provider_retryable_failure"
                        if exc.retryable
                        else "llm_provider_response_format_failure"
                    ),
                    "retryable": exc.retryable,
                    "retry_after_seconds": retry_after_seconds,
                    "attempt": attempt,
                    "max_attempts": max_attempts,
                    "provider_stage": exc.provider_stage,
                    "upstream_status_code": None,
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
