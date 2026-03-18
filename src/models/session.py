from typing import Annotated, List, Literal

from pydantic import BaseModel, Field, StringConstraints

from src.models.scenario import Audience


SessionStatus = Literal["active", "paused", "completed"]
NonEmptyStr = Annotated[str, StringConstraints(min_length=1)]
ShortText = Annotated[str, StringConstraints(min_length=2)]


class ParticipantActionLog(BaseModel):
    turn: int = Field(ge=1)
    summary: ShortText


class ExerciseLogItem(BaseModel):
    turn: int = Field(ge=1)
    type: ShortText
    text: ShortText


class SessionMetrics(BaseModel):
    impact_level: int = Field(ge=1, le=5)
    media_pressure: int = Field(ge=0)
    service_disruption: int = Field(ge=0)
    leadership_pressure: int = Field(ge=0)
    public_confusion: int = Field(ge=0)
    attack_surface: int = Field(ge=0)


class SessionFlags(BaseModel):
    executive_escalation: bool = False
    external_comms_sent: bool = False
    forensic_analysis_started: bool = False
    external_access_restricted: bool = False


class SessionState(BaseModel):
    session_id: NonEmptyStr
    scenario_id: NonEmptyStr
    scenario_version: NonEmptyStr
    audience: Audience
    status: SessionStatus = "active"
    current_time: Annotated[str, StringConstraints(min_length=4)]
    turn_number: int = Field(ge=0)
    phase: ShortText
    known_facts: List[NonEmptyStr] = Field(default_factory=list)
    unknowns: List[NonEmptyStr] = Field(default_factory=list)
    participant_actions: List[ParticipantActionLog] = Field(default_factory=list)
    decisions: List[NonEmptyStr] = Field(default_factory=list)
    consequences: List[NonEmptyStr] = Field(default_factory=list)
    active_injects: List[NonEmptyStr] = Field(default_factory=list)
    resolved_injects: List[NonEmptyStr] = Field(default_factory=list)
    metrics: SessionMetrics
    flags: SessionFlags = Field(default_factory=SessionFlags)
    focus_items: List[NonEmptyStr] = Field(default_factory=list)
    exercise_log: List[ExerciseLogItem] = Field(default_factory=list)
    no_communication_turns: int = Field(default=0, ge=0)
