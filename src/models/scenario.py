from typing import Dict, List, Literal
from pydantic import BaseModel, Field


Difficulty = Literal['low', 'medium', 'high']
Audience = Literal['krisledning', 'it-ledning', 'kommunikation']


class Background(BaseModel):
    organization_type: str
    context: str
    threat_actor: str
    assumptions: List[str] = Field(default_factory=list)


class InitialState(BaseModel):
    time: str
    phase: str
    known_facts: List[str] = Field(default_factory=list)
    unknowns: List[str] = Field(default_factory=list)
    affected_systems: List[str] = Field(default_factory=list)
    business_impact: List[str] = Field(default_factory=list)
    impact_level: int = Field(ge=1, le=5)


class Actor(BaseModel):
    id: str
    name: str
    role: str


class InjectDefinition(BaseModel):
    id: str
    type: str
    title: str
    description: str
    trigger_conditions: List[str] = Field(default_factory=list)
    audience_relevance: List[Audience] = Field(default_factory=list)
    severity: int = Field(ge=1, le=5)


class RuleDefinition(BaseModel):
    id: str
    name: str
    conditions: List[str] = Field(default_factory=list)
    effects: List[str] = Field(default_factory=list)


class PresentationGuideline(BaseModel):
    focus: List[str] = Field(default_factory=list)
    tone: str


class Scenario(BaseModel):
    id: str
    title: str
    version: str
    description: str
    audiences: List[Audience]
    training_goals: List[str]
    difficulty: Difficulty
    timebox_minutes: int = Field(gt=0)
    background: Background
    initial_state: InitialState
    actors: List[Actor] = Field(default_factory=list)
    inject_catalog: List[InjectDefinition] = Field(default_factory=list)
    rules: List[RuleDefinition] = Field(default_factory=list)
    presentation_guidelines: Dict[Audience, PresentationGuideline]
