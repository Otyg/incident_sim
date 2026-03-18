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

from typing import Annotated, Dict, List, Literal

from pydantic import BaseModel, Field, StringConstraints


Difficulty = Literal["low", "medium", "high"]
Audience = Literal["krisledning", "it-ledning", "kommunikation"]
InjectType = Literal["media", "executive", "operations", "technical", "stakeholder"]
NonEmptyStr = Annotated[str, StringConstraints(min_length=1)]
ShortText = Annotated[str, StringConstraints(min_length=2)]
TextBlock = Annotated[str, StringConstraints(min_length=3)]
GoalText = Annotated[str, StringConstraints(min_length=3)]


class Background(BaseModel):
    organization_type: ShortText
    context: TextBlock
    threat_actor: ShortText
    assumptions: List[NonEmptyStr] = Field(default_factory=list)


class InitialState(BaseModel):
    time: Annotated[str, StringConstraints(min_length=4)]
    phase: ShortText
    known_facts: List[NonEmptyStr] = Field(default_factory=list)
    unknowns: List[NonEmptyStr] = Field(default_factory=list)
    affected_systems: List[NonEmptyStr] = Field(default_factory=list)
    business_impact: List[NonEmptyStr] = Field(default_factory=list)
    impact_level: int = Field(ge=1, le=5)


class Actor(BaseModel):
    id: NonEmptyStr
    name: ShortText
    role: ShortText


class InjectDefinition(BaseModel):
    id: NonEmptyStr
    type: InjectType
    title: ShortText
    description: TextBlock
    trigger_conditions: List[NonEmptyStr] = Field(default_factory=list)
    audience_relevance: List[Audience] = Field(default_factory=list)
    severity: int = Field(ge=1, le=5)


class RuleDefinition(BaseModel):
    id: NonEmptyStr
    name: ShortText
    conditions: List[NonEmptyStr] = Field(default_factory=list)
    effects: List[NonEmptyStr] = Field(default_factory=list)


class PresentationGuideline(BaseModel):
    focus: List[NonEmptyStr] = Field(default_factory=list)
    tone: ShortText


class Scenario(BaseModel):
    id: NonEmptyStr
    title: ShortText
    version: NonEmptyStr
    description: TextBlock
    audiences: List[Audience] = Field(min_length=1)
    training_goals: List[GoalText] = Field(min_length=1)
    difficulty: Difficulty
    timebox_minutes: int = Field(ge=1, le=480)
    background: Background
    initial_state: InitialState
    actors: List[Actor] = Field(default_factory=list)
    inject_catalog: List[InjectDefinition] = Field(default_factory=list)
    rules: List[RuleDefinition] = Field(default_factory=list)
    presentation_guidelines: Dict[Audience, PresentationGuideline]
