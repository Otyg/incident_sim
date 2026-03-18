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
    organization_type: ShortText = Field(
        description="Typ av organisation som övningen utgår från, till exempel kommun eller myndighet."
    )
    context: TextBlock = Field(
        description="Bakgrundsbeskrivning som sätter scenen inför övningen."
    )
    threat_actor: ShortText = Field(
        description="Kort beskrivning av aktören bakom hotet eller incidenten."
    )
    assumptions: List[NonEmptyStr] = Field(
        default_factory=list,
        description="Antaganden som gäller när scenariot startar, till exempel tekniska eller organisatoriska förutsättningar.",
    )


class InitialState(BaseModel):
    time: Annotated[str, StringConstraints(min_length=4)] = Field(
        description="Starttid för scenariot, normalt i formatet HH:MM."
    )
    phase: ShortText = Field(
        description=(
            "Maskinläsbart namn på startfasen, till exempel initial-detection, "
            "containment eller recovery. Fasen är idag författningsmetadata och "
            "används inte för dynamisk faslogik i backend."
        )
    )
    known_facts: List[NonEmptyStr] = Field(
        default_factory=list,
        description="Det deltagarna känner till när övningen startar.",
    )
    unknowns: List[NonEmptyStr] = Field(
        default_factory=list,
        description="Viktiga osäkerheter som fortfarande behöver utredas.",
    )
    affected_systems: List[NonEmptyStr] = Field(
        default_factory=list,
        description="System eller tjänster som redan bedöms vara påverkade vid start.",
    )
    business_impact: List[NonEmptyStr] = Field(
        default_factory=list,
        description="Beskrivning av verksamhetspåverkan i scenariots initiala läge.",
    )
    impact_level: int = Field(
        ge=1,
        le=5,
        description=(
            "Övergripande påverkan i startläget på en femgradig skala där 1 är "
            "mycket begränsad påverkan och 5 är samhälls- eller verksamhetskritisk påverkan."
        ),
    )


class Actor(BaseModel):
    id: NonEmptyStr = Field(
        description="Stabilt unikt id för aktören, till exempel actor-ciso."
    )
    name: ShortText = Field(description="Visningsnamn för aktören.")
    role: ShortText = Field(
        description="Kort beskrivning av aktörens ansvar eller funktion i övningen."
    )


class InjectDefinition(BaseModel):
    id: NonEmptyStr = Field(
        description="Stabilt unikt id för injectet, till exempel inject-media-001."
    )
    type: InjectType = Field(
        description="Vilken typ av inject det är, till exempel media eller operations."
    )
    title: ShortText = Field(description="Kort rubrik för injectet.")
    description: TextBlock = Field(
        description="Beskrivning av vad injectet tillför till övningen."
    )
    trigger_conditions: List[NonEmptyStr] = Field(
        default_factory=list,
        description=(
            "Mänskligt läsbara villkor eller signaler som beskriver när injectet är "
            "tänkt att användas. Dessa utvärderas inte dynamiskt av backend idag."
        ),
    )
    audience_relevance: List[Audience] = Field(
        default_factory=list,
        description="Vilka målgrupper injectet främst är relevant för."
    )
    severity: int = Field(
        ge=1,
        le=5,
        description=(
            "Hur skarpt injectet är på en femgradig skala där 1 är låg störning och "
            "5 är mycket kritiskt eller omedelbart handlingsdrivande."
        ),
    )


class RuleDefinition(BaseModel):
    id: NonEmptyStr = Field(
        description="Stabilt unikt id för regeln, till exempel rule-escalation."
    )
    name: ShortText = Field(description="Kort namn på regeln.")
    conditions: List[NonEmptyStr] = Field(
        default_factory=list,
        description=(
            "Mänskligt läsbara villkor för när regeln borde slå till. Fälten "
            "dokumenterar scenariots avsikt och exekveras inte generiskt av backend idag."
        ),
    )
    effects: List[NonEmptyStr] = Field(
        default_factory=list,
        description=(
            "Mänskligt läsbar beskrivning av regelns tänkta effekt i scenariot."
        ),
    )


class PresentationGuideline(BaseModel):
    focus: List[NonEmptyStr] = Field(
        default_factory=list,
        description="Vilka aspekter som bör betonas för målgruppen."
    )
    tone: ShortText = Field(
        description="Vilken tonalitet eller nivå presentationen bör ha för målgruppen."
    )


class Scenario(BaseModel):
    id: NonEmptyStr = Field(
        description="Globalt unikt scenario-id som används vid lagring och hämtning."
    )
    title: ShortText = Field(description="Scenarioets visningsnamn.")
    version: NonEmptyStr = Field(
        description="Scenarioets versionsbeteckning, till exempel 1.0."
    )
    description: TextBlock = Field(
        description="Kort sammanfattning av scenarioets upplägg och kontext."
    )
    audiences: List[Audience] = Field(
        min_length=1,
        description="Vilka målgrupper scenariot är avsett för."
    )
    training_goals: List[GoalText] = Field(
        min_length=1,
        description="Vilka förmågor eller lärandemål scenariot ska öva."
    )
    difficulty: Difficulty = Field(
        description="Övergripande svårighetsgrad för scenariot."
    )
    timebox_minutes: int = Field(
        ge=1,
        le=480,
        description="Planerad maximal övningstid i minuter."
    )
    background: Background = Field(
        description="Bakgrund och grundförutsättningar för scenariot."
    )
    initial_state: InitialState = Field(
        description="Vilket läge övningen startar i."
    )
    actors: List[Actor] = Field(
        default_factory=list,
        description="Viktiga aktörer eller roller i scenariot."
    )
    inject_catalog: List[InjectDefinition] = Field(
        default_factory=list,
        description="Katalog över möjliga injects som kan användas under övningen."
    )
    rules: List[RuleDefinition] = Field(
        default_factory=list,
        description=(
            "Dokumenterade scenarioregler och samband. Dessa är idag i första hand "
            "författningsstöd och exekveras inte generiskt från scenariot."
        ),
    )
    presentation_guidelines: Dict[Audience, PresentationGuideline] = Field(
        description="Hur scenariot bör presenteras för respektive målgrupp."
    )
