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
    turn: int = Field(ge=0)
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
