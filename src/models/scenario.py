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

import json
from pathlib import Path
from typing import Any, Literal

from jsonschema import Draft202012Validator
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from pydantic_core import PydanticCustomError

from src.schemas.narrator_response import NarratorResponse

Difficulty = str
Audience = str
InjectType = str
RulePriority = Literal["low", "medium", "high"]
RuleTrigger = Literal["session_started", "turn_processed"]
ConditionOperator = Literal[
    "equals",
    "not_equals",
    "gte",
    "lte",
    "contains",
    "not_contains",
]
ConditionFact = Literal[
    "state.phase",
    "state.metrics.impact_level",
    "state.metrics.media_pressure",
    "state.metrics.service_disruption",
    "state.metrics.leadership_pressure",
    "state.metrics.public_confusion",
    "state.metrics.attack_surface",
    "state.flags.executive_escalation",
    "state.flags.external_comms_sent",
    "state.flags.forensic_analysis_started",
    "state.flags.external_access_restricted",
    "session.turn_number",
    "action.action_types",
    "action.targets",
]
EffectType = Literal[
    "set_phase",
    "add_active_inject",
    "resolve_inject",
    "append_focus_item",
    "append_consequence",
    "increment_metric",
    "set_flag",
    "append_exercise_log",
]
MetricPath = Literal[
    "state.metrics.impact_level",
    "state.metrics.media_pressure",
    "state.metrics.service_disruption",
    "state.metrics.leadership_pressure",
    "state.metrics.public_confusion",
    "state.metrics.attack_surface",
]
FlagPath = Literal[
    "state.flags.executive_escalation",
    "state.flags.external_comms_sent",
    "state.flags.forensic_analysis_started",
    "state.flags.external_access_restricted",
]


SCENARIO_SCHEMA_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "scenarios" / "scenario.schema.json"
)


def load_scenario_json_schema() -> dict[str, Any]:
    """Load the checked-in scenario JSON Schema."""

    with SCENARIO_SCHEMA_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def validate_scenario_payload(payload: Any) -> Any:
    """Validate raw scenario input against the JSON Schema source of truth."""

    schema = load_scenario_json_schema()
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(payload), key=lambda error: list(error.path))
    if not errors:
        return payload

    first_error = errors[0]
    location = ".".join(str(part) for part in first_error.absolute_path) or "root"
    raise PydanticCustomError(
        "scenario_json_schema",
        f"Scenario does not match JSON Schema at {location}: {first_error.message}",
    )


class Background(BaseModel):
    model_config = ConfigDict(extra="allow")

    organization_type: str = Field(
        description="Typ av organisation som övningen utgår från, till exempel kommun eller myndighet."
    )
    context: str = Field(
        description="Bakgrundsbeskrivning som sätter scenen inför övningen."
    )
    threat_actor: str = Field(
        description="Kort beskrivning av aktören bakom hotet eller incidenten."
    )
    assumptions: list[str] = Field(
        default_factory=list,
        description="Antaganden som gäller när scenariot startar, till exempel tekniska eller organisatoriska förutsättningar.",
    )


class InitialState(BaseModel):
    model_config = ConfigDict(extra="allow")

    class InitialNarrationConfig(BaseModel):
        model_config = ConfigDict(extra="forbid")

        default: NarratorResponse | None = Field(
            default=None,
            description="Gemensamt startnarrativ som används när ingen audience-specifik variant finns.",
        )
        by_audience: dict[str, NarratorResponse] = Field(
            default_factory=dict,
            description="Valfria audience-specifika startnarrativ som prioriteras före default.",
        )

        @model_validator(mode="after")
        def ensure_narrative_available(self) -> "InitialState.InitialNarrationConfig":
            """Require at least one narrative source."""

            if self.default is None and not self.by_audience:
                raise ValueError(
                    "initial_narration must define default or at least one by_audience entry"
                )
            return self

    time: str = Field(description="Starttid för scenariot, normalt i formatet HH:MM.")
    phase: str = Field(
        description=(
            "Maskinläsbart namn på startfasen, till exempel initial-detection, "
            "containment eller recovery. Fasen är idag författningsmetadata och "
            "används inte för dynamisk faslogik i backend."
        )
    )
    known_facts: list[str] = Field(
        default_factory=list,
        description="Det deltagarna känner till när övningen startar.",
    )
    unknowns: list[str] = Field(
        default_factory=list,
        description="Viktiga osäkerheter som fortfarande behöver utredas.",
    )
    affected_systems: list[str] = Field(
        default_factory=list,
        description="System eller tjänster som redan bedöms vara påverkade vid start.",
    )
    business_impact: list[str] = Field(
        default_factory=list,
        description="Beskrivning av verksamhetspåverkan i scenariots initiala läge.",
    )
    impact_level: int = Field(
        description=(
            "Övergripande påverkan i startläget på en femgradig skala där 1 är "
            "mycket begränsad påverkan och 5 är samhälls- eller verksamhetskritisk påverkan."
        ),
    )
    initial_narration: InitialNarrationConfig = Field(
        description=(
            "Fördefinierat startnarrativ för scenariot. Audience-specifika varianter "
            "prioriteras före default när sessionen startas."
        )
    )


class Actor(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = Field(
        description="Stabilt unikt id för aktören, till exempel actor-ciso."
    )
    name: str = Field(description="Visningsnamn för aktören.")
    role: str = Field(
        description="Kort beskrivning av aktörens ansvar eller funktion i övningen."
    )


class InjectDefinition(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = Field(
        description="Stabilt unikt id för injectet, till exempel inject-media-001."
    )
    type: InjectType = Field(
        description="Vilken typ av inject det är, till exempel media eller operations."
    )
    title: str = Field(description="Kort rubrik för injectet.")
    description: str = Field(
        description="Beskrivning av vad injectet tillför till övningen."
    )
    trigger_conditions: list[str] = Field(
        default_factory=list,
        description=(
            "Mänskligt läsbara villkor eller signaler som beskriver när injectet är "
            "tänkt att användas. Dessa utvärderas inte dynamiskt av backend idag."
        ),
    )
    audience_relevance: list[Audience] = Field(
        default_factory=list,
        description="Vilka målgrupper injectet främst är relevant för.",
    )
    severity: int = Field(
        description=(
            "Hur skarpt injectet är på en femgradig skala där 1 är låg störning och "
            "5 är mycket kritiskt eller omedelbart handlingsdrivande."
        ),
    )


class RuleDefinition(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = Field(
        description="Stabilt unikt id för regeln, till exempel rule-escalation."
    )
    name: str = Field(description="Kort namn på regeln.")
    conditions: list[str] = Field(
        default_factory=list,
        description=(
            "Mänskligt läsbara villkor för när regeln borde slå till. Fälten "
            "dokumenterar scenariots avsikt och exekveras inte generiskt av backend idag."
        ),
    )
    effects: list[str] = Field(
        default_factory=list,
        description=(
            "Mänskligt läsbar beskrivning av regelns tänkta effekt i scenariot."
        ),
    )


class ExecutableRuleCondition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fact: ConditionFact = Field(
        description="Vilket state- eller actionfält som villkoret läser."
    )
    operator: ConditionOperator = Field(
        description="Vilken jämförelseoperator som ska användas."
    )
    value: str | int | bool = Field(description="Vilket värde villkoret jämför mot.")


class ScenarioRuleEffect(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: EffectType = Field(
        description="Vilken typ av deterministisk effekt som ska utföras."
    )
    phase: str | None = Field(
        default=None,
        description="Ny fas för effekttypen set_phase.",
    )
    inject_id: str | None = Field(
        default=None,
        description="Inject-id för add_active_inject eller resolve_inject.",
    )
    item: str | None = Field(
        default=None,
        description="Textinnehåll för append_focus_item eller append_consequence.",
    )
    metric: MetricPath | None = Field(
        default=None,
        description="Vilket metricsfält som påverkas av increment_metric.",
    )
    amount: int | None = Field(
        default=None,
        description="Hur mycket ett metricsfält ska ökas eller minskas.",
    )
    flag: FlagPath | None = Field(
        default=None,
        description="Vilken flagga som sätts av set_flag.",
    )
    value: bool | None = Field(
        default=None,
        description="Booleskt värde för set_flag.",
    )
    message: str | None = Field(
        default=None,
        description="Loggmeddelande för append_exercise_log.",
    )
    log_type: str | None = Field(
        default=None,
        description="Övningsloggtyp för append_exercise_log.",
    )


class ExecutableRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Stabilt unikt id för den exekverbara regeln.")
    name: str = Field(description="Kort namn på den exekverbara regeln.")
    trigger: RuleTrigger = Field(
        description="Vilken händelse som ska utlösa regelutvärderingen."
    )
    conditions: list[ExecutableRuleCondition] = Field(
        default_factory=list,
        description="Strukturerade villkor som alla måste vara uppfyllda för att regeln ska slå till.",
    )
    effects: list[ScenarioRuleEffect] = Field(
        min_length=1,
        description="Deterministiska effekter som utförs när regeln träffar.",
    )
    priority: RulePriority = Field(
        default="medium",
        description="Prioritet för exekvering när flera regler matchar samma trigger.",
    )
    once: bool = Field(
        default=False,
        description="Om true får regeln bara appliceras en gång per session.",
    )


class PresentationGuideline(BaseModel):
    model_config = ConfigDict(extra="allow")

    focus: list[str] = Field(
        default_factory=list,
        description="Vilka aspekter som bör betonas för målgruppen.",
    )
    tone: str = Field(
        description="Vilken tonalitet eller nivå presentationen bör ha för målgruppen."
    )


class Scenario(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = Field(
        description="Globalt unikt scenario-id som används vid lagring och hämtning."
    )
    title: str = Field(description="Scenarioets visningsnamn.")
    version: str = Field(
        description="Scenarioets versionsbeteckning, till exempel 1.0."
    )
    description: str = Field(
        description="Kort sammanfattning av scenarioets upplägg och kontext."
    )
    audiences: list[Audience] = Field(
        description="Vilka målgrupper scenariot är avsett för."
    )
    training_goals: list[str] = Field(
        description="Vilka förmågor eller lärandemål scenariot ska öva."
    )
    difficulty: Difficulty = Field(
        description="Övergripande svårighetsgrad för scenariot."
    )
    timebox_minutes: int = Field(description="Planerad maximal övningstid i minuter.")
    background: Background = Field(
        description="Bakgrund och grundförutsättningar för scenariot."
    )
    initial_state: InitialState = Field(description="Vilket läge övningen startar i.")
    actors: list[Actor] = Field(
        default_factory=list, description="Viktiga aktörer eller roller i scenariot."
    )
    inject_catalog: list[InjectDefinition] = Field(
        default_factory=list,
        description="Katalog över möjliga injects som kan användas under övningen.",
    )
    rules: list[RuleDefinition] = Field(
        default_factory=list,
        description=(
            "Dokumenterade scenarioregler och samband. Dessa är idag i första hand "
            "författningsstöd och exekveras inte generiskt från scenariot."
        ),
    )
    executable_rules: list[ExecutableRule] = Field(
        default_factory=list,
        description=(
            "Strukturerade och exekverbara scenarioregler för den datadrivna "
            "scenariomotorn."
        ),
    )
    presentation_guidelines: dict[str, PresentationGuideline] = Field(
        description="Hur scenariot bör presenteras för respektive målgrupp."
    )

    @model_validator(mode="before")
    @classmethod
    def enforce_json_schema(cls, value: Any) -> Any:
        """Use the checked-in JSON Schema as the source of truth."""

        return validate_scenario_payload(value)

    @classmethod
    def model_json_schema(cls, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Expose the checked-in JSON Schema as the model schema."""

        return load_scenario_json_schema()
