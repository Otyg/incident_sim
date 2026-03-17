from typing import Dict, List, Literal
from pydantic import BaseModel, Field

from app.models.scenario import Audience


SessionStatus = Literal['active', 'paused', 'completed']


class ParticipantActionLog(BaseModel):
    turn: int = Field(ge=1)
    summary: str


class ExerciseLogItem(BaseModel):
    turn: int = Field(ge=1)
    type: str
    text: str


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
    session_id: str
    scenario_id: str
    scenario_version: str
    audience: Audience
    status: SessionStatus = 'active'
    current_time: str
    turn_number: int = Field(ge=0)
    phase: str
    known_facts: List[str] = Field(default_factory=list)
    unknowns: List[str] = Field(default_factory=list)
    participant_actions: List[ParticipantActionLog] = Field(default_factory=list)
    decisions: List[str] = Field(default_factory=list)
    consequences: List[str] = Field(default_factory=list)
    active_injects: List[str] = Field(default_factory=list)
    resolved_injects: List[str] = Field(default_factory=list)
    metrics: SessionMetrics
    flags: SessionFlags = Field(default_factory=SessionFlags)
    focus_items: List[str] = Field(default_factory=list)
    exercise_log: List[ExerciseLogItem] = Field(default_factory=list)
    no_communication_turns: int = Field(default=0, ge=0)
