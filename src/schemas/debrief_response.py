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

"""Schema for structured debrief material after session completion."""

from typing import Annotated, List

from pydantic import BaseModel, Field, StringConstraints


PointText = Annotated[str, StringConstraints(min_length=1)]
ShortText = Annotated[str, StringConstraints(min_length=2)]
TextBlock = Annotated[str, StringConstraints(min_length=3)]


class DebriefTimelineEntry(BaseModel):
    """One summarized timeline entry in the generated debrief."""

    turn_number: int = Field(ge=1)
    summary: ShortText
    outcome: TextBlock


class DebriefResponse(BaseModel):
    """Validated debrief response returned when a session is completed."""

    exercise_summary: str = Field(min_length=10)
    timeline_summary: List[DebriefTimelineEntry] = Field(min_length=1, max_length=8)
    strengths: List[PointText] = Field(min_length=2, max_length=6)
    development_areas: List[PointText] = Field(min_length=2, max_length=6)
    debrief_questions: List[PointText] = Field(min_length=3, max_length=8)
    recommended_follow_ups: List[PointText] = Field(default_factory=list, max_length=6)
    facilitator_notes: str = Field(min_length=5)
