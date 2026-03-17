from typing import List, Literal
from pydantic import BaseModel, Field


InjectType = Literal['media', 'executive', 'operations', 'technical', 'stakeholder']


class NarratorInject(BaseModel):
    type: InjectType
    title: str = Field(min_length=2)
    message: str = Field(min_length=3)


class NarratorResponse(BaseModel):
    situation_update: str = Field(min_length=10)
    key_points: List[str] = Field(min_length=2, max_length=5)
    new_consequences: List[str] = Field(default_factory=list)
    injects: List[NarratorInject] = Field(default_factory=list, max_length=2)
    decisions_to_consider: List[str] = Field(default_factory=list)
    facilitator_notes: str = Field(min_length=5)
