from typing import Annotated, List, Literal

from pydantic import BaseModel, Field, StringConstraints


ActionType = Literal[
    "containment",
    "coordination",
    "communication",
    "escalation",
    "analysis",
    "recovery",
    "monitoring",
    "legal",
    "business_continuity",
]

Priority = Literal["low", "medium", "high"]
NonEmptyStr = Annotated[str, StringConstraints(min_length=1)]


class InterpretedAction(BaseModel):
    action_summary: str = Field(min_length=3)
    action_types: List[ActionType] = Field(min_length=1)
    targets: List[NonEmptyStr] = Field(default_factory=list)
    intent: str = Field(min_length=3)
    expected_effects: List[NonEmptyStr] = Field(default_factory=list)
    risks: List[NonEmptyStr] = Field(default_factory=list)
    uncertainties: List[NonEmptyStr] = Field(default_factory=list)
    priority: Priority
    confidence: float = Field(ge=0.0, le=1.0)
