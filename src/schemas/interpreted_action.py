from typing import List, Literal
from pydantic import BaseModel, Field


ActionType = Literal[
    'containment',
    'coordination',
    'communication',
    'escalation',
    'analysis',
    'recovery',
    'monitoring',
    'legal',
    'business_continuity',
]

Priority = Literal['low', 'medium', 'high']


class InterpretedAction(BaseModel):
    action_summary: str = Field(min_length=3)
    action_types: List[ActionType] = Field(min_length=1)
    targets: List[str] = Field(default_factory=list)
    intent: str = Field(min_length=3)
    expected_effects: List[str] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)
    uncertainties: List[str] = Field(default_factory=list)
    priority: Priority
    confidence: float = Field(ge=0.0, le=1.0)
