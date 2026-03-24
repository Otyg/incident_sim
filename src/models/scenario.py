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

"""Scenario domain models and JSON Schema-backed validation helpers."""

import json
from pathlib import Path
from typing import Any, Literal, get_args

from jsonschema import Draft202012Validator
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError

from src.schemas.interpreted_action import ActionType
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
    "state.no_communication_turns",
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
TextMatcherField = Literal["action.action_types", "action.targets"]
TextMatcherMatchType = Literal["contains_any", "contains_all"]


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
    """Background context that frames the scenario before the exercise starts."""

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


class StateNarrationConfig(BaseModel):
    """Scenario-authored narration variants for a specific state."""

    model_config = ConfigDict(extra="forbid")

    default: NarratorResponse | None = Field(
        default=None,
        description="Gemensamt narrativ som används när ingen audience-specifik variant finns.",
    )
    by_audience: dict[str, NarratorResponse] = Field(
        default_factory=dict,
        description="Valfria audience-specifika narrativ som prioriteras före default.",
    )

    @model_validator(mode="after")
    def ensure_narrative_available(self) -> "StateNarrationConfig":
        """Require at least one narrative source."""

        if self.default is None and not self.by_audience:
            raise ValueError(
                "narration must define default or at least one by_audience entry"
            )
        return self


class ScenarioStateDefinition(BaseModel):
    """Definition of a single scenario state or phase snapshot."""

    model_config = ConfigDict(extra="allow")

    id: str = Field(
        description="Stabilt unikt state-id, till exempel state-initial-detection."
    )
    phase: str = Field(
        description=(
            "Maskinläsbart namn på fasen eller state-läget, till exempel "
            "initial-detection, escalation eller containment."
        )
    )
    title: str = Field(description="Kort visningsnamn för state-läget.")
    description: str = Field(
        description="Beskrivning av vad state-läget representerar i scenariot."
    )
    time: str | None = Field(
        default=None,
        description="Tid för state-läget när det används som komplett state-definition.",
    )
    known_facts: list[str] | None = Field(
        default=None,
        description="Det deltagarna känner till i detta state-läge.",
    )
    unknowns: list[str] | None = Field(
        default=None,
        description="Viktiga osäkerheter i detta state-läge.",
    )
    affected_systems: list[str] | None = Field(
        default=None,
        description="System eller tjänster som bedöms vara påverkade i detta state-läge.",
    )
    business_impact: list[str] | None = Field(
        default=None,
        description="Beskrivning av verksamhetspåverkan i detta state-läge.",
    )
    impact_level: int | None = Field(
        default=None,
        description=(
            "Övergripande påverkan i state-läget på en femgradig skala där 1 är "
            "mycket begränsad påverkan och 5 är samhälls- eller verksamhetskritisk påverkan."
        ),
    )
    narration: StateNarrationConfig | None = Field(
        default=None,
        description=(
            "Fördefinierat narrativ för state-läget. Audience-specifika varianter "
            "prioriteras före default."
        ),
    )


class Actor(BaseModel):
    """Named actor participating in or affecting the scenario."""

    model_config = ConfigDict(extra="allow")

    id: str = Field(
        description="Stabilt unikt id för aktören, till exempel actor-ciso."
    )
    name: str = Field(description="Visningsnamn för aktören.")
    role: str = Field(
        description="Kort beskrivning av aktörens ansvar eller funktion i övningen."
    )


class InjectDefinition(BaseModel):
    """Definition of a facilitator inject available during the exercise."""

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
    trigger_constraints: "InjectTriggerConstraints | None" = Field(
        default=None,
        description=(
            "Valfria begränsningar för när injectet får triggas, till exempel "
            "att det blockeras efter att andra injects triggats."
        ),
    )


class InjectTriggerConstraints(BaseModel):
    """Declarative trigger constraints for inject activation."""

    model_config = ConfigDict(extra="forbid")

    blocked_if_triggered_any: list[str] = Field(
        default_factory=list,
        description=(
            "Lista över inject-id som blockerar detta inject om de någon gång "
            "har triggats i sessionen."
        ),
    )

    @model_validator(mode="after")
    def normalize_constraints(self) -> "InjectTriggerConstraints":
        """Normalize and deduplicate constraint ids."""

        seen: set[str] = set()
        normalized: list[str] = []
        for item in self.blocked_if_triggered_any:
            candidate = item.strip()
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)
            normalized.append(candidate)
        self.blocked_if_triggered_any = normalized
        return self


class TextMatcher(BaseModel):
    """Declarative text matcher used to enrich interpreted actions."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Stabilt unikt id för textmatcharen.")
    field: TextMatcherField = Field(
        description="Vilket tolkningsfält som ska kompletteras vid match."
    )
    match_type: TextMatcherMatchType = Field(
        description="Hur deltagartexten ska matchas mot angivna mönster."
    )
    patterns: list[str] = Field(
        min_length=1,
        description="Case-insensitive textmönster som används mot rå deltagartext.",
    )
    value: str = Field(
        min_length=1,
        description="Vilket värde som ska läggas till i angivet tolkningsfält vid träff.",
    )

    @model_validator(mode="after")
    def validate_field_value_combo(self) -> "TextMatcher":
        """Ensure matcher values are valid for the selected target field."""

        if self.field == "action.action_types" and self.value not in get_args(
            ActionType
        ):
            raise ValueError(
                "TextMatcher value must be a supported action type when field is action.action_types"
            )
        return self


class InterpretationHintCondition(BaseModel):
    """Conditions that decide when a scenario interpretation hint applies."""

    model_config = ConfigDict(extra="forbid")

    text_contains_any: list[str] = Field(
        default_factory=list,
        description="Rå deltagartext måste innehålla minst ett av dessa textmönster.",
    )
    action_types_contains: list[ActionType] = Field(
        default_factory=list,
        description="Redan tolkade action_types som måste finnas innan hinton används.",
    )
    targets_contains: list[str] = Field(
        default_factory=list,
        description="Redan tolkade targets som måste finnas innan hinton används.",
    )

    @model_validator(mode="after")
    def require_at_least_one_condition(self) -> "InterpretationHintCondition":
        """Require at least one explicit condition for the hint."""

        if not (
            self.text_contains_any
            or self.action_types_contains
            or self.targets_contains
        ):
            raise ValueError(
                "InterpretationHintCondition must define at least one condition"
            )
        return self


class InterpretationHint(BaseModel):
    """Scenario-authored hint that adds structured interpretation metadata."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Stabilt unikt id för tolkstödet.")
    when: InterpretationHintCondition = Field(
        description="Villkor som måste vara uppfyllda för att hinton ska användas."
    )
    add_action_types: list[ActionType] = Field(
        default_factory=list,
        description="Action types som adderas om hinton träffar.",
    )
    add_targets: list[str] = Field(
        default_factory=list,
        description="Targets som adderas om hinton träffar.",
    )
    confidence_boost: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description=(
            "Valfritt metadatafält för framtida användning när tolkstöd ska kunna "
            "påverka confidence. Används inte dynamiskt ännu."
        ),
    )

    @model_validator(mode="after")
    def require_at_least_one_effect(self) -> "InterpretationHint":
        """Require at least one additiv effekt for the hint."""

        if not (self.add_action_types or self.add_targets):
            raise ValueError(
                "InterpretationHint must define add_action_types or add_targets"
            )
        return self


class TargetAlias(BaseModel):
    """Canonical target name together with accepted alias spellings."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Stabilt unikt id för target-normaliseringen.")
    canonical: str = Field(
        min_length=1,
        description="Det kanoniska target-värdet som regler och hints ska använda.",
    )
    aliases: list[str] = Field(
        min_length=1,
        description=(
            "Case-insensitive alias eller fraser som ska normaliseras till det "
            "kanoniska target-värdet."
        ),
    )

    @model_validator(mode="after")
    def require_non_empty_aliases(self) -> "TargetAlias":
        """Require at least one non-empty alias value."""

        if not any(alias.strip() for alias in self.aliases):
            raise ValueError("TargetAlias aliases must contain at least one value")
        return self


class RuleDefinition(BaseModel):
    """Human-readable legacy rule description stored with the scenario."""

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
    """Machine-readable condition within an executable scenario rule."""

    model_config = ConfigDict(extra="forbid")

    fact: ConditionFact = Field(
        description="Vilket state- eller actionfält som villkoret läser."
    )
    operator: ConditionOperator = Field(
        description="Vilken jämförelseoperator som ska användas."
    )
    value: str | int | bool = Field(description="Vilket värde villkoret jämför mot.")


class ScenarioRuleEffect(BaseModel):
    """Machine-readable effect executed when a scenario rule matches."""

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
    """Executable scenario rule evaluated by the deterministic engine."""

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
    """Audience-specific guidance for presenting the scenario."""

    model_config = ConfigDict(extra="allow")

    focus: list[str] = Field(
        default_factory=list,
        description="Vilka aspekter som bör betonas för målgruppen.",
    )
    tone: str = Field(
        description="Vilken tonalitet eller nivå presentationen bör ha för målgruppen."
    )


class PromptInstructionSet(BaseModel):
    """Reusable prompt instruction payload for global or audience-specific use."""

    model_config = ConfigDict(extra="forbid")

    text: str | None = Field(
        default=None,
        description="Fri text med promptinstruktioner som adderas till default-promptar.",
    )
    items: list[str] = Field(
        default_factory=list,
        description=(
            "Punktlista med promptinstruktioner. Tomma eller whitespace-rader ignoreras."
        ),
    )

    @model_validator(mode="after")
    def normalize_and_require_content(self) -> "PromptInstructionSet":
        """Normalize whitespace and require at least one usable instruction."""

        normalized_text = self.text.strip() if isinstance(self.text, str) else ""
        normalized_items = [item.strip() for item in self.items if item.strip()]

        self.text = normalized_text or None
        self.items = normalized_items
        if self.text is None and not self.items:
            raise ValueError(
                "PromptInstructionSet must define non-empty text or at least one non-empty items entry"
            )
        return self

    def to_lines(self) -> list[str]:
        """Render instruction content as ordered text lines."""

        lines: list[str] = []
        if self.text:
            lines.extend(
                line.strip() for line in self.text.splitlines() if line.strip()
            )
        lines.extend(self.items)
        return lines


class PromptInstructionsConfig(BaseModel):
    """Scenario-level prompt instruction configuration."""

    model_config = ConfigDict(extra="forbid")

    default: PromptInstructionSet | None = Field(
        default=None,
        description="Instruktioner som alltid adderas till narration- och debrief-promptarna.",
    )
    by_audience: dict[Audience, PromptInstructionSet] = Field(
        default_factory=dict,
        description=(
            "Audience-specifika instruktioner som adderas efter default-instruktionerna."
        ),
    )

    @model_validator(mode="after")
    def require_any_instruction_source(self) -> "PromptInstructionsConfig":
        """Require at least one instruction source when the object is present."""

        if self.default is None and not self.by_audience:
            raise ValueError(
                "prompt_instructions must define default or at least one by_audience entry"
            )
        return self

    def resolve_lines_for_audience(self, audience: Audience) -> list[str]:
        """Resolve ordered instruction lines for a target audience."""

        lines: list[str] = []
        if self.default is not None:
            lines.extend(self.default.to_lines())
        audience_specific = self.by_audience.get(audience)
        if audience_specific is not None:
            lines.extend(audience_specific.to_lines())
        return lines


class NarrationBasePrompt(BaseModel):
    """Structured base prompt for narration containing scenario context."""

    model_config = ConfigDict(extra="forbid")

    base: str = Field(
        description="Core context and situation description for the exercise."
    )
    audience: list[str] = Field(description="Target audiences for the exercise.")
    training_goals: list[str] = Field(
        description="Learning objectives and goals of the exercise."
    )
    assumptions: list[str] = Field(
        description="Assumptions and limitations that apply to the scenario."
    )


class NarrationPromptProfile(BaseModel):
    """Narration-specific scenario prompt profile with base and phase overrides."""

    model_config = ConfigDict(extra="forbid")

    base: PromptInstructionSet | None = Field(
        default=None,
        description="Basinstruktioner för narration som gäller oavsett fas.",
    )
    by_phase: dict[str, PromptInstructionSet] = Field(
        default_factory=dict,
        description="Fas-specifika narration-instruktioner som adderas efter base.",
    )

    @model_validator(mode="after")
    def require_any_source(self) -> "NarrationPromptProfile":
        """Require at least one prompt source."""

        if self.base is None and not self.by_phase:
            raise ValueError("NarrationPromptProfile must define base or by_phase")
        return self


class PromptProfilesConfig(BaseModel):
    """Scenario-level prompt profiles grouped by LLM stage."""

    model_config = ConfigDict(extra="forbid")

    narration: NarrationPromptProfile | None = Field(
        default=None,
        description="Scenariospecifik promptprofil för narration.",
    )

    @model_validator(mode="after")
    def require_any_profile(self) -> "PromptProfilesConfig":
        """Require at least one configured profile."""

        if self.narration is None:
            raise ValueError("prompt_profiles must define at least one profile")
        return self


class Scenario(BaseModel):
    """Top-level persisted scenario document used by the application."""

    model_config = ConfigDict(extra="allow")

    id: str = Field(
        description="Globalt unikt scenario-id som används vid lagring och hämtning."
    )
    original_text: str | None = Field(
        default=None,
        description=(
            "Valfri ursprungstext från scenarioförfattaren, till exempel markdown "
            "som användes för att generera scenario-JSON."
        ),
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
    states: list[ScenarioStateDefinition] = Field(
        min_length=1,
        description="Ordnad lista över scenariots definierade state-lägen där första posten är startläget.",
    )
    actors: list[Actor] = Field(
        default_factory=list, description="Viktiga aktörer eller roller i scenariot."
    )
    inject_catalog: list[InjectDefinition] = Field(
        default_factory=list,
        description="Katalog över möjliga injects som kan användas under övningen.",
    )
    text_matchers: list[TextMatcher] = Field(
        default_factory=list,
        description=(
            "Enkla, scenariodefinierade textmatchningar mot rå deltagartext som "
            "kan komplettera tolkade action_types eller targets."
        ),
    )
    target_aliases: list[TargetAlias] = Field(
        default_factory=list,
        description=(
            "Scenariodefinierade alias för att normalisera provider-targets och "
            "rå deltagartext till kanoniska target-värden innan regler utvärderas."
        ),
    )
    interpretation_hints: list[InterpretationHint] = Field(
        default_factory=list,
        description=(
            "Deklarativa tolkhints som kan komplettera LLM-tolkningen med "
            "ytterligare action_types eller targets när deras villkor matchar."
        ),
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
    narration_base_prompt: NarrationBasePrompt | None = Field(
        default=None,
        description="Structured base prompt for narration containing scenario context, audience, goals, and assumptions.",
    )
    prompt_instructions: PromptInstructionsConfig | None = Field(
        default=None,
        description=(
            "Valfria scenariospecifika tilläggsinstruktioner som adderas till "
            "narration- och debrief-promptarna."
        ),
    )
    prompt_profiles: PromptProfilesConfig | None = Field(
        default=None,
        description=(
            "Valfria stage-specifika promptprofiler. I v1 används narration med "
            "base och by_phase."
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def enforce_json_schema(cls, value: Any) -> Any:
        """Use the checked-in JSON Schema as the source of truth."""

        return validate_scenario_payload(value)

    @model_validator(mode="after")
    def validate_phase_timeline(self) -> "Scenario":
        """Ensure state timeline is internally consistent."""

        state_ids = [state.id for state in self.states]
        if len(state_ids) != len(set(state_ids)):
            raise ValueError("Scenario states must use unique ids")

        phase_ids = [state.phase for state in self.states]
        if len(phase_ids) != len(set(phase_ids)):
            raise ValueError("Scenario states must use unique phases")

        text_matcher_ids = [matcher.id for matcher in self.text_matchers]
        if len(text_matcher_ids) != len(set(text_matcher_ids)):
            raise ValueError("Scenario text_matchers must use unique ids")

        target_alias_ids = [alias.id for alias in self.target_aliases]
        if len(target_alias_ids) != len(set(target_alias_ids)):
            raise ValueError("Scenario target_aliases must use unique ids")

        interpretation_hint_ids = [hint.id for hint in self.interpretation_hints]
        if len(interpretation_hint_ids) != len(set(interpretation_hint_ids)):
            raise ValueError("Scenario interpretation_hints must use unique ids")

        inject_ids = [inject.id for inject in self.inject_catalog]
        if len(inject_ids) != len(set(inject_ids)):
            raise ValueError("Scenario inject_catalog must use unique ids")
        inject_id_set = set(inject_ids)

        initial_state = self.states[0]
        if initial_state.time is None:
            raise ValueError("states[0] must define time")
        if initial_state.impact_level is None:
            raise ValueError("states[0] must define impact_level")
        if initial_state.narration is None:
            raise ValueError("states[0] must define narration")

        for inject in self.inject_catalog:
            constraints = inject.trigger_constraints
            if constraints is None:
                continue
            for blocked_id in constraints.blocked_if_triggered_any:
                if blocked_id not in inject_id_set:
                    raise ValueError(
                        f"Inject {inject.id} references unknown blocked inject {blocked_id}"
                    )

        for rule in self.executable_rules:
            for effect in rule.effects:
                if (
                    effect.type == "set_phase"
                    and effect.phase
                    and effect.phase not in phase_ids
                ):
                    raise ValueError(
                        f"Executable rule {rule.id} references undefined phase {effect.phase}"
                    )

        narration_profile = (
            self.prompt_profiles.narration if self.prompt_profiles is not None else None
        )
        if narration_profile is not None:
            for profile_phase in narration_profile.by_phase:
                if profile_phase not in phase_ids:
                    raise ValueError(
                        f"prompt_profiles.narration.by_phase references undefined phase {profile_phase}"
                    )

        return self

    def resolve_prompt_instruction_lines(self, audience: Audience) -> list[str]:
        """Resolve ordered scenario prompt instruction lines for an audience."""

        if self.prompt_instructions is None:
            return []
        return self.prompt_instructions.resolve_lines_for_audience(audience)

    def resolve_narration_prompt_lines(
        self, audience: Audience, phase: str
    ) -> list[str]:
        """Resolve narration prompt lines from narration_base_prompt and legacy fallback."""

        lines: list[str] = []

        # Use new narration_base_prompt if available
        if self.narration_base_prompt is not None:
            lines.append(f"Base:\n{self.narration_base_prompt.base}")
            lines.append(
                "Audience:\n"
                + "\n".join(f"- {a}" for a in self.narration_base_prompt.audience)
            )
            lines.append(
                "Training goals:\n"
                + "\n".join(f"- {g}" for g in self.narration_base_prompt.training_goals)
            )
            lines.append(
                "Assumptions:\n"
                + "\n".join(f"- {a}" for a in self.narration_base_prompt.assumptions)
            )
        else:
            # Fallback to legacy prompt_profiles
            narration_profile = (
                self.prompt_profiles.narration
                if self.prompt_profiles is not None
                else None
            )
            if narration_profile is not None:
                if narration_profile.base is not None:
                    lines.extend(narration_profile.base.to_lines())
                phase_specific = narration_profile.by_phase.get(phase)
                if phase_specific is not None:
                    lines.extend(phase_specific.to_lines())

        lines.extend(self.resolve_prompt_instruction_lines(audience))
        return lines

    def get_inject_definition(self, inject_id: str) -> InjectDefinition | None:
        """Return the inject definition with matching id, if available."""

        return next(
            (inject for inject in self.inject_catalog if inject.id == inject_id), None
        )

    def resolve_blocking_inject(
        self, target_inject_id: str, triggered_injects: list[str]
    ) -> str | None:
        """Resolve the first blocking inject id based on trigger constraints."""

        inject = self.get_inject_definition(target_inject_id)
        if inject is None or inject.trigger_constraints is None:
            return None

        triggered_set = set(triggered_injects)
        for blocked_id in inject.trigger_constraints.blocked_if_triggered_any:
            if blocked_id in triggered_set:
                return blocked_id
        return None

    @classmethod
    def model_json_schema(cls, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Expose the checked-in JSON Schema as the model schema."""

        return load_scenario_json_schema()
