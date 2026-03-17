from typing import Annotated, List, Literal

from pydantic import BaseModel, Field, StringConstraints


InjectType = Literal['media', 'executive', 'operations', 'technical', 'stakeholder']
PointText = Annotated[str, StringConstraints(min_length=1)]
ShortText = Annotated[str, StringConstraints(min_length=2)]
TextBlock = Annotated[str, StringConstraints(min_length=3)]


class NarratorInject(BaseModel):
    type: InjectType
    title: ShortText
    message: TextBlock


class NarratorResponse(BaseModel):
    situation_update: str = Field(min_length=10)
    key_points: List[PointText] = Field(min_length=2, max_length=5)
    new_consequences: List[PointText] = Field(default_factory=list)
    injects: List[NarratorInject] = Field(default_factory=list, max_length=2)
    decisions_to_consider: List[PointText] = Field(default_factory=list)
    facilitator_notes: str = Field(min_length=5)
