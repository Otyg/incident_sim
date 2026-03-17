from pydantic import BaseModel, Field

from src.models.session import SessionState
from src.schemas.interpreted_action import InterpretedAction
from src.schemas.narrator_response import NarratorResponse


class Turn(BaseModel):
    turn_number: int = Field(ge=1)
    participant_input: str = Field(min_length=3)
    interpreted_action: InterpretedAction
    state_snapshot: SessionState
    narrator_response: NarratorResponse
