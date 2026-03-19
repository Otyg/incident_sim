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

"""Provider abstractions and schema validation helpers for LLM output.

The module is the central integration point for runtime LLM access. It defines:
- the provider interface used by the API layer
- configuration loading from ``config.yaml``
- concrete runtime providers such as Ollama
- validation wrappers that convert raw provider payloads into typed Pydantic
  models

To add a new provider, a developer typically needs to:
1. implement ``LLMProvider``
2. add a configuration section under ``llm_provider`` in ``config.yaml``
3. extend ``get_llm_provider()`` so the new provider can be selected
4. keep provider output schema-compatible so existing validation still works
"""

import json
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any
import unicodedata

from pydantic import ValidationError
import yaml

from src.logging_utils import get_logger
from src.models.session import SessionState
from src.models.turn import Turn
from src.models.scenario import Scenario
from src.schemas.debrief_response import DebriefResponse
from src.schemas.interpreted_action import InterpretedAction
from src.schemas.narrator_response import NarratorResponse


PROMPTS_DIR = Path(__file__).resolve().parents[2] / "data" / "prompts"
CONFIG_PATH = Path(__file__).resolve().parents[2] / "config.yaml"
logger = get_logger(__name__)


class LLMProviderError(Exception):
    """Base exception for provider-related failures."""

    pass


class ProviderUpstreamError(LLMProviderError):
    """Raised when an upstream LLM provider request fails."""

    def __init__(
        self,
        message: str,
        *,
        provider_stage: str,
        upstream_status_code: int | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.provider_stage = provider_stage
        self.upstream_status_code = upstream_status_code
        self.retryable = retryable


class ProviderOutputValidationError(LLMProviderError):
    """Raised when provider output cannot be validated against schemas."""

    pass


class ProviderConfigurationError(LLMProviderError):
    """Raised when provider configuration is unsupported or unavailable."""

    pass


class ProviderResponseFormatError(LLMProviderError):
    """Raised when provider text output cannot be parsed into JSON."""

    pass


class LLMProvider(ABC):
    """Abstract interface for action interpretation and narration providers.

    Every runtime provider must implement the same two operations:
    - ``interpret_action`` for transforming participant free text into a
      structured action payload
    - ``generate_narration`` for turning a session state into a structured
      narration payload

    The returned dictionaries are intentionally raw. They are validated later
    through Pydantic schemas so all providers share the same output contract.
    """

    @abstractmethod
    def interpret_action(self, participant_input: str) -> dict[str, Any]:
        """Interpret participant free text into structured action data.

        Args:
            participant_input: Free-text participant action to interpret.

        Returns:
            dict[str, Any]: Raw structured payload to validate as an
                ``InterpretedAction``.
        """

        raise NotImplementedError

    @abstractmethod
    def generate_narration(self, state: SessionState) -> dict[str, Any]:
        """Generate narration from a session state snapshot.

        Args:
            state: Session state after rules have been applied.

        Returns:
            dict[str, Any]: Raw structured payload to validate as a
                ``NarratorResponse``.
        """

        raise NotImplementedError

    @abstractmethod
    def generate_debrief(
        self, scenario: Scenario, state: SessionState, timeline: list[Turn]
    ) -> dict[str, Any]:
        """Generate a debrief from scenario, final state and timeline."""

        raise NotImplementedError

    @abstractmethod
    def generate_scenario_draft(
        self, source_text: str, source_format: str = "markdown"
    ) -> dict[str, Any]:
        """Generate a scenario draft from author-provided source text."""

        raise NotImplementedError


def load_prompt(name: str) -> str:
    """Load a prompt file from the prompt directory.

    Args:
        name: File name of the prompt to load.

    Returns:
        str: Prompt contents as UTF-8 text.

    Raises:
        FileNotFoundError: If the prompt file does not exist.
    """

    return (PROMPTS_DIR / name).read_text(encoding="utf-8").strip()


def load_config(path: Path | None = None) -> dict[str, Any]:
    """Load application configuration from ``config.yaml``.

    Args:
        path: Path to the YAML configuration file.

    Returns:
        dict[str, Any]: Parsed configuration document.

    Raises:
        ProviderConfigurationError: If the file is missing or invalid.
    """

    config_path = path or CONFIG_PATH

    if not config_path.exists():
        logger.error("LLM configuration file was not found: %s", config_path)
        raise ProviderConfigurationError(f"Configuration file not found: {config_path}")

    try:
        with config_path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
    except yaml.YAMLError as exc:
        logger.error(
            "Failed to parse LLM configuration from %s",
            config_path,
            exc_info=True,
        )
        raise ProviderConfigurationError(
            f"Invalid YAML configuration in {config_path}"
        ) from exc

    if not isinstance(data, dict):
        logger.error("LLM configuration root was not a mapping in %s", config_path)
        raise ProviderConfigurationError(
            f"Configuration root must be a mapping in {config_path}"
        )

    logger.info("Loaded application configuration from %s", config_path)
    return data


def load_llm_config(path: Path | None = None) -> dict[str, Any]:
    """Load the LLM-specific configuration section.

    Args:
        path: Path to the YAML configuration file.

    Returns:
        dict[str, Any]: LLM provider configuration mapping.

    Raises:
        ProviderConfigurationError: If the ``llm_provider`` section is missing.

    Notes:
        The expected structure is a top-level ``llm_provider`` mapping with a
        ``provider`` selector and one nested mapping per supported provider,
        for example ``ollama`` or ``openai``.
    """

    data = load_config(path)
    llm_config = data.get("llm_provider")

    if not isinstance(llm_config, dict):
        logger.error("Missing or invalid llm_provider section in config.yaml")
        raise ProviderConfigurationError(
            "Missing or invalid llm_provider section in config.yaml"
        )

    logger.info("Loaded llm_provider configuration")
    return llm_config


def validate_interpreted_action(payload: dict[str, Any]) -> InterpretedAction:
    """Validate raw provider output as an interpreted action.

    Args:
        payload: Raw provider payload for action interpretation.

    Returns:
        InterpretedAction: Validated interpreted action.

    Raises:
        ProviderOutputValidationError: If the payload does not satisfy the
            action schema.
    """

    try:
        return InterpretedAction.model_validate(payload)
    except ValidationError as exc:
        logger.warning(
            "Provider output did not validate as interpreted action: %s",
            payload,
            exc_info=True,
        )
        raise ProviderOutputValidationError(
            "Invalid interpreted action payload"
        ) from exc


def validate_narration(payload: dict[str, Any]) -> NarratorResponse:
    """Validate raw provider output as a narration payload.

    Args:
        payload: Raw provider payload for narration generation.

    Returns:
        NarratorResponse: Validated narration payload.

    Raises:
        ProviderOutputValidationError: If the payload does not satisfy the
            narration schema.
    """

    normalized_payload = payload
    if isinstance(payload, dict):
        normalized_payload = dict(payload)

        if isinstance(normalized_payload.get("key_points"), list):
            key_points = normalized_payload["key_points"]
            if len(key_points) > 5:
                logger.warning(
                    "Narration payload contained too many key_points; trimming from %s to 5",
                    len(key_points),
                )
                normalized_payload["key_points"] = key_points[:5]

        if isinstance(normalized_payload.get("injects"), list):
            injects = normalized_payload["injects"]
            if len(injects) > 2:
                logger.warning(
                    "Narration payload contained too many injects; trimming from %s to 2",
                    len(injects),
                )
                normalized_payload["injects"] = injects[:2]

    try:
        return NarratorResponse.model_validate(normalized_payload)
    except ValidationError as exc:
        logger.warning(
            "Provider output did not validate as narration payload: %s",
            normalized_payload,
            exc_info=True,
        )
        raise ProviderOutputValidationError("Invalid narration payload") from exc


def validate_debrief(payload: dict[str, Any]) -> DebriefResponse:
    """Validate raw provider output as a debrief payload."""

    try:
        return DebriefResponse.model_validate(payload)
    except ValidationError as exc:
        logger.warning(
            "Provider output did not validate as debrief payload: %s",
            payload,
            exc_info=True,
        )
        raise ProviderOutputValidationError("Invalid debrief payload") from exc


def validate_scenario(payload: dict[str, Any]) -> Scenario:
    """Validate raw provider output as a scenario payload."""

    normalized_payload = payload
    if isinstance(payload, dict):
        normalized_payload = normalize_scenario_payload(payload)

    try:
        return Scenario.model_validate(normalized_payload)
    except ValidationError as exc:
        logger.warning(
            "Provider output did not validate as scenario payload: %s",
            normalized_payload,
            exc_info=True,
        )
        raise ProviderOutputValidationError("Invalid scenario payload") from exc


def normalize_scenario_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Best-effort normalization for scenario drafts returned by an LLM.

    The authoring flow should stay conservative and schema-safe. If the model
    emits incomplete executable rules, we downgrade them into documentation
    rules instead of failing the entire draft.
    """

    normalized = dict(payload)
    if isinstance(normalized.get("id"), str):
        normalized["id"] = _sanitize_identifier(
            normalized["id"], fallback="scenario-draft"
        )

    for list_field in (
        "actors",
        "inject_catalog",
        "text_matchers",
        "target_aliases",
        "interpretation_hints",
        "rules",
        "executable_rules",
    ):
        value = normalized.get(list_field)
        if value is None:
            normalized[list_field] = []

    rules = normalized.get("rules")
    normalized_rules = list(rules) if isinstance(rules, list) else []
    known_phases = _normalize_states(normalized)
    _ensure_initial_state_complete(normalized)
    _normalize_entity_ids(normalized, "actors", fallback_prefix="actor")
    _normalize_entity_ids(normalized, "inject_catalog", fallback_prefix="inject")
    _normalize_entity_ids(normalized, "text_matchers", fallback_prefix="matcher")
    _normalize_entity_ids(normalized, "target_aliases", fallback_prefix="alias")
    _normalize_entity_ids(normalized, "interpretation_hints", fallback_prefix="hint")
    _normalize_entity_ids(normalized, "rules", fallback_prefix="rule")

    executable_rules = normalized.get("executable_rules")
    if isinstance(executable_rules, list):
        valid_executable_rules: list[Any] = []
        downgraded_count = 0
        seen_rule_ids: set[str] = set()

        for index, rule in enumerate(executable_rules):
            if not isinstance(rule, dict):
                downgraded_count += 1
                continue

            normalized_rule = dict(rule)
            normalized_rule["id"] = _ensure_unique_identifier(
                _sanitize_identifier(
                    str(normalized_rule.get("id") or f"rule-draft-{index + 1}"),
                    fallback=f"rule-draft-{index + 1}",
                ),
                seen_rule_ids,
            )
            if isinstance(normalized_rule.get("effects"), list):
                normalized_rule["effects"] = _normalize_rule_effects(
                    normalized_rule["effects"], known_phases
                )
            if isinstance(normalized_rule.get("conditions"), list):
                normalized_rule["conditions"] = _normalize_rule_conditions(
                    normalized_rule["conditions"]
                )
            elif "conditions" in normalized_rule:
                normalized_rule["conditions"] = []

            has_trigger = isinstance(normalized_rule.get("trigger"), str) and bool(
                normalized_rule.get("trigger")
            )
            has_effects = (
                isinstance(normalized_rule.get("effects"), list)
                and len(normalized_rule.get("effects")) > 0
            )

            if has_trigger and has_effects:
                valid_executable_rules.append(normalized_rule)
                continue

            downgraded_count += 1
            normalized_rules.append(
                {
                    "id": normalized_rule["id"],
                    "name": str(
                        normalized_rule.get("name")
                        or normalized_rule.get("title")
                        or f"Utkastregel {index + 1}"
                    ),
                    "conditions": _string_list_from_unknown(
                        normalized_rule.get("conditions")
                    ),
                    "effects": _string_list_from_unknown(
                        normalized_rule.get("effects")
                    ),
                }
            )

        if downgraded_count:
            logger.warning(
                "Scenario payload contained %s incomplete executable_rules; downgraded them to documentation rules",
                downgraded_count,
            )

        normalized["executable_rules"] = valid_executable_rules

    normalized["rules"] = normalized_rules
    return normalized


def _normalize_states(payload: dict[str, Any]) -> set[str]:
    """Normalize state ids/phases and ensure phases stay unique."""

    states = payload.get("states")
    if not isinstance(states, list):
        return set()

    seen_state_ids: set[str] = set()
    seen_phases: set[str] = set()
    known_phases: set[str] = set()

    for index, state in enumerate(states):
        if not isinstance(state, dict):
            continue

        title = str(state.get("title") or "")
        fallback_state_id = (
            f"state-{_sanitize_identifier(title, fallback=f'phase-{index + 1}')}"
        )
        state["id"] = _ensure_unique_identifier(
            _sanitize_identifier(
                str(state.get("id") or fallback_state_id),
                fallback=fallback_state_id,
            ),
            seen_state_ids,
        )

        phase_seed = state.get("phase") or title or f"phase-{index + 1}"
        state["phase"] = _ensure_unique_identifier(
            _sanitize_identifier(str(phase_seed), fallback=f"phase-{index + 1}"),
            seen_phases,
        )
        _normalize_state_narration(state)
        known_phases.add(state["phase"])

    return known_phases


def _ensure_initial_state_complete(payload: dict[str, Any]) -> None:
    """Ensure the first state satisfies runtime-required fields."""

    states = payload.get("states")
    if not isinstance(states, list) or not states or not isinstance(states[0], dict):
        return

    initial_state = states[0]
    source_text = payload.get("original_text")

    if (
        not isinstance(initial_state.get("time"), str)
        or not initial_state.get("time").strip()
    ):
        initial_state["time"] = _extract_time_from_text(source_text) or "08:00"

    impact_level = initial_state.get("impact_level")
    if not isinstance(impact_level, int) or not (1 <= impact_level <= 5):
        initial_state["impact_level"] = 3

    narration = initial_state.get("narration")
    if not isinstance(narration, dict) or not narration:
        initial_state["narration"] = _build_default_state_narration(initial_state)
        return

    default_narration = narration.get("default")
    by_audience = narration.get("by_audience")
    has_default = isinstance(default_narration, dict)
    has_by_audience = isinstance(by_audience, dict) and bool(by_audience)
    if not has_default and not has_by_audience:
        initial_state["narration"] = _build_default_state_narration(initial_state)


def _extract_time_from_text(source_text: Any) -> str | None:
    """Extract the first HH:MM-style time from source text if present."""

    if not isinstance(source_text, str):
        return None

    match = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", source_text)
    if not match:
        return None

    hour = int(match.group(1))
    minute = int(match.group(2))
    return f"{hour:02d}:{minute:02d}"


def _build_default_state_narration(state: dict[str, Any]) -> dict[str, Any]:
    """Build a minimal valid narration block for a generated initial state."""

    title = str(state.get("title") or "Initialt läge")
    description = str(
        state.get("description") or "Scenariot har gått in i ett initialt läge."
    )
    known_facts = state.get("known_facts")
    unknowns = state.get("unknowns")
    business_impact = state.get("business_impact")

    key_points: list[str] = []
    if isinstance(known_facts, list):
        key_points.extend(
            [str(item).strip() for item in known_facts if str(item).strip()]
        )
    if isinstance(unknowns, list) and unknowns:
        key_points.append(f"Osäkerhet kvarstår: {str(unknowns[0]).strip()}")
    if len(key_points) < 2 and isinstance(business_impact, list) and business_impact:
        key_points.append(str(business_impact[0]).strip())
    while len(key_points) < 2:
        key_points.append("Lägesbilden behöver fortsatt verifieras.")

    decisions_to_consider = []
    if isinstance(unknowns, list) and unknowns:
        decisions_to_consider.append("Vilken information behöver verifieras först?")
    if isinstance(business_impact, list) and business_impact:
        decisions_to_consider.append(
            "Vilka verksamheter behöver prioriteras omedelbart?"
        )
    if not decisions_to_consider:
        decisions_to_consider.append("Vilken första åtgärd bör prioriteras nu?")

    return {
        "default": {
            "situation_update": f"{title}: {description}",
            "key_points": key_points[:5],
            "new_consequences": [],
            "injects": [],
            "decisions_to_consider": decisions_to_consider[:5],
            "facilitator_notes": "Startnarrativet kompletterades automatiskt för att ge ett giltigt scenarioutkast.",
        }
    }


def _normalize_state_narration(state: dict[str, Any]) -> None:
    """Normalize state narration into schema-compatible object form."""

    narration = state.get("narration")
    if narration is None:
        return

    if isinstance(narration, str):
        text = narration.strip()
        if not text:
            state["narration"] = None
            return

        state["narration"] = {
            "default": {
                "situation_update": text,
                "key_points": _build_key_points_from_text(text),
                "new_consequences": [],
                "injects": [],
                "decisions_to_consider": [
                    "Vilken åtgärd eller prioritering behöver beslutas i detta läge?"
                ],
                "facilitator_notes": "Narrativet omvandlades automatiskt från fritext till giltig struktur.",
            }
        }
        return

    if not isinstance(narration, dict):
        state["narration"] = None
        return

    default = narration.get("default")
    if isinstance(default, str):
        text = default.strip()
        if text:
            narration["default"] = {
                "situation_update": text,
                "key_points": _build_key_points_from_text(text),
                "new_consequences": [],
                "injects": [],
                "decisions_to_consider": [
                    "Vilken åtgärd eller prioritering behöver beslutas i detta läge?"
                ],
                "facilitator_notes": "Narrativet omvandlades automatiskt från fritext till giltig struktur.",
            }
        else:
            narration.pop("default", None)

    by_audience = narration.get("by_audience")
    if isinstance(by_audience, dict):
        for audience, audience_value in list(by_audience.items()):
            if isinstance(audience_value, str):
                text = audience_value.strip()
                if not text:
                    by_audience.pop(audience, None)
                    continue
                by_audience[audience] = {
                    "situation_update": text,
                    "key_points": _build_key_points_from_text(text),
                    "new_consequences": [],
                    "injects": [],
                    "decisions_to_consider": [
                        "Vilken åtgärd eller prioritering behöver beslutas i detta läge?"
                    ],
                    "facilitator_notes": "Narrativet omvandlades automatiskt från fritext till giltig struktur.",
                }


def _build_key_points_from_text(text: str) -> list[str]:
    """Create a compact valid key_points list from free-text narration."""

    parts = [
        part.strip(" -.:;")
        for part in re.split(r"[.!?]\s+|\n+", text)
        if part and part.strip(" -.:;")
    ]
    key_points = parts[:5]
    while len(key_points) < 2:
        key_points.append("Lägesbilden behöver fortsatt verifieras.")
    return key_points


def _normalize_entity_ids(
    payload: dict[str, Any], field_name: str, *, fallback_prefix: str
) -> None:
    """Normalize ids for list-based scenario entities."""

    items = payload.get(field_name)
    if not isinstance(items, list):
        return

    seen_ids: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue

        item["id"] = _ensure_unique_identifier(
            _sanitize_identifier(
                str(item.get("id") or f"{fallback_prefix}-{index + 1}"),
                fallback=f"{fallback_prefix}-{index + 1}",
            ),
            seen_ids,
        )


def _normalize_rule_effects(effects: list[Any], known_phases: set[str]) -> list[Any]:
    """Normalize executable rule effects and drop invalid phase references."""

    normalized_effects: list[Any] = []
    for effect in effects:
        if not isinstance(effect, dict):
            continue

        normalized_effect = dict(effect)
        effect_type = normalized_effect.get("type")
        if not isinstance(effect_type, str):
            continue

        if effect_type == "set_phase":
            phase = normalized_effect.get("phase")
            if not isinstance(phase, str):
                continue
            sanitized_phase = _sanitize_identifier(phase, fallback="")
            if not sanitized_phase or sanitized_phase not in known_phases:
                continue
            normalized_effect["phase"] = sanitized_phase

        elif effect_type in {"add_active_inject", "resolve_inject"}:
            inject_id = normalized_effect.get("inject_id")
            if not isinstance(inject_id, str) or not inject_id.strip():
                fallback_inject_id = normalized_effect.get("value")
                if isinstance(fallback_inject_id, str) and fallback_inject_id.strip():
                    inject_id = fallback_inject_id
            if not isinstance(inject_id, str) or not inject_id.strip():
                continue
            normalized_effect["inject_id"] = _sanitize_identifier(
                inject_id,
                fallback=inject_id,
            )
            normalized_effect.pop("value", None)

        elif effect_type in {"append_focus_item", "append_consequence"}:
            item = normalized_effect.get("item")
            if not isinstance(item, str) or not item.strip():
                continue
            normalized_effect["item"] = item.strip()

        elif effect_type == "increment_metric":
            metric = normalized_effect.get("metric")
            amount = normalized_effect.get("amount")
            if metric not in {
                "state.metrics.impact_level",
                "state.metrics.media_pressure",
                "state.metrics.service_disruption",
                "state.metrics.leadership_pressure",
                "state.metrics.public_confusion",
                "state.metrics.attack_surface",
            }:
                continue
            if not isinstance(amount, int):
                continue

        elif effect_type == "set_flag":
            flag = normalized_effect.get("flag")
            value = normalized_effect.get("value")
            if flag not in {
                "state.flags.executive_escalation",
                "state.flags.external_comms_sent",
                "state.flags.forensic_analysis_started",
                "state.flags.external_access_restricted",
            }:
                continue
            if not isinstance(value, bool):
                continue

        elif effect_type == "append_exercise_log":
            message = normalized_effect.get("message")
            if not isinstance(message, str) or not message.strip():
                continue
            normalized_effect["message"] = message.strip()
            log_type = normalized_effect.get("log_type")
            if log_type is not None and not (
                isinstance(log_type, str) and log_type.strip()
            ):
                normalized_effect.pop("log_type", None)

        else:
            continue

        normalized_effects.append(normalized_effect)

    return normalized_effects


def _normalize_rule_conditions(conditions: list[Any]) -> list[Any]:
    """Normalize executable rule conditions and drop unsupported facts."""

    allowed_facts = {
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
    }
    allowed_operators = {
        "equals",
        "not_equals",
        "gte",
        "lte",
        "contains",
        "not_contains",
    }

    normalized_conditions: list[Any] = []
    for condition in conditions:
        if not isinstance(condition, dict):
            continue

        fact = condition.get("fact")
        operator = condition.get("operator")
        value = condition.get("value")

        if fact not in allowed_facts:
            continue
        if operator not in allowed_operators:
            continue
        if not isinstance(value, (str, int, bool)):
            continue
        if isinstance(value, str) and not value.strip():
            continue

        normalized_conditions.append(
            {
                "fact": fact,
                "operator": operator,
                "value": value.strip() if isinstance(value, str) else value,
            }
        )

    return normalized_conditions


def _sanitize_identifier(value: str, *, fallback: str) -> str:
    """Convert arbitrary model text to a conservative ASCII identifier."""

    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    ascii_value = ascii_value.lower()
    ascii_value = re.sub(r"https?://\S+", " ", ascii_value)
    ascii_value = re.sub(r"[^a-z0-9]+", "-", ascii_value)
    ascii_value = ascii_value.strip("-")
    ascii_value = re.sub(r"-{2,}", "-", ascii_value)
    return ascii_value or fallback


def _ensure_unique_identifier(value: str, seen: set[str]) -> str:
    """Make an identifier unique within a local collection."""

    candidate = value
    suffix = 2
    while candidate in seen:
        candidate = f"{value}-{suffix}"
        suffix += 1
    seen.add(candidate)
    return candidate


def _string_list_from_unknown(value: Any) -> list[str]:
    """Convert unknown provider output into a compact list of strings."""

    if not isinstance(value, list):
        return []

    result: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            result.append(item.strip())
        elif isinstance(item, dict):
            parts = []
            for key in (
                "type",
                "fact",
                "operator",
                "value",
                "phase",
                "inject_id",
                "item",
                "message",
                "log_type",
            ):
                current = item.get(key)
                if current is not None and str(current).strip():
                    parts.append(f"{key}={current}")
            if parts:
                result.append(", ".join(parts))

    return result


class OllamaProvider(LLMProvider):
    """Runtime provider backed by the official Ollama Python client.

    The provider supports:
    - local Ollama via ``host: http://localhost:11434``
    - Ollama Cloud via ``host: https://ollama.com`` together with ``api_key``

    It requests JSON-only responses and parses them into Python dictionaries
    before schema validation happens in the API layer.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """Create an Ollama-backed runtime provider from config data.

        Args:
            config: Mapping from ``config.yaml`` under ``llm_provider.ollama``.
                Supported keys are ``host``, ``api_key``, ``model``,
                ``interpret_model`` and ``narration_model``.
        """

        self.interpret_prompt = load_prompt("interpret_action.txt")
        self.narration_prompt = load_prompt("generate_narration.txt")
        self.debrief_prompt = load_prompt("generate_debrief.txt")
        self.scenario_authoring_prompt = load_prompt("generate_scenario_draft.txt")
        self.host = str(config.get("host") or "http://localhost:11434")
        self.default_model = str(config.get("model") or "llama3.2")
        self.interpret_model = str(config.get("interpret_model") or self.default_model)
        self.narration_model = str(config.get("narration_model") or self.default_model)
        self.scenario_model = str(config.get("scenario_model") or self.default_model)
        self.api_key = config.get("api_key")
        self.client = self._create_client(self.host, self._build_headers())
        logger.info(
            "Initialized OllamaProvider host=%s interpret_model=%s narration_model=%s scenario_model=%s",
            self.host,
            self.interpret_model,
            self.narration_model,
            self.scenario_model,
        )

    @staticmethod
    def _create_client(host: str, headers: dict[str, str] | None):
        """Create an Ollama client instance.

        Args:
            host: Base URL for the Ollama endpoint.
            headers: Optional headers applied to each request.

        Returns:
            Any: Instantiated Ollama client.

        Raises:
            ProviderConfigurationError: If the Ollama package is not installed.
        """

        try:
            from ollama import Client
        except ImportError as exc:
            raise ProviderConfigurationError(
                "The ollama package is required for OllamaProvider. Install it with pip install ollama."
            ) from exc

        return Client(host=host, headers=headers or None)

    def _build_headers(self) -> dict[str, str] | None:
        """Build optional authorization headers for Ollama requests.

        Returns:
            dict[str, str] | None: Authorization headers when an API key is
                configured, otherwise ``None``.
        """

        if not self.api_key:
            return None

        return {"Authorization": f"Bearer {self.api_key}"}

    @staticmethod
    def _extract_json_payload(response: Any) -> dict[str, Any]:
        """Extract and parse JSON content from an Ollama chat response.

        Args:
            response: Response object returned by the Ollama client.

        Returns:
            dict[str, Any]: Parsed JSON payload.

        Raises:
            ProviderResponseFormatError: If the response content is missing or
                cannot be parsed as a JSON object.
        """

        response_dump = None
        if hasattr(response, "model_dump"):
            try:
                response_dump = response.model_dump()
            except Exception:
                response_dump = None
        elif isinstance(response, dict):
            response_dump = response

        candidate_contents: list[str] = []

        message = getattr(response, "message", None)
        if message is None and isinstance(response_dump, dict):
            message = response_dump.get("message")

        if message is not None:
            content = getattr(message, "content", None)
            thinking = getattr(message, "thinking", None)
            if isinstance(message, dict):
                content = content or message.get("content")
                thinking = thinking or message.get("thinking")
            if isinstance(content, str) and content.strip():
                candidate_contents.append(content)
            if isinstance(thinking, str) and thinking.strip():
                candidate_contents.append(thinking)

        if isinstance(response_dump, dict):
            for key in ("content", "response", "message"):
                value = response_dump.get(key)
                if isinstance(value, str) and value.strip():
                    candidate_contents.append(value)
                elif isinstance(value, dict):
                    nested_content = value.get("content")
                    nested_thinking = value.get("thinking")
                    if isinstance(nested_content, str) and nested_content.strip():
                        candidate_contents.append(nested_content)
                    if isinstance(nested_thinking, str) and nested_thinking.strip():
                        candidate_contents.append(nested_thinking)

        stripped = None
        for candidate in candidate_contents:
            if isinstance(candidate, str) and candidate.strip():
                stripped = candidate.strip()
                break

        if not stripped:
            raise ProviderResponseFormatError(
                "Ollama response did not contain message content"
            )
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            start = stripped.find("{")
            end = stripped.rfind("}")
            if start == -1 or end == -1 or end <= start:
                raise ProviderResponseFormatError(
                    "Ollama response was not valid JSON"
                ) from None

            try:
                parsed = json.loads(stripped[start : end + 1])
            except json.JSONDecodeError as exc:
                raise ProviderResponseFormatError(
                    "Ollama response was not valid JSON"
                ) from exc

        if not isinstance(parsed, dict):
            raise ProviderResponseFormatError("Ollama response JSON must be an object")

        return parsed

    @staticmethod
    def _extract_status_code(exc: Exception) -> int | None:
        """Best-effort extraction of an HTTP status code from a client exception."""

        for attribute in ("status_code", "status", "code"):
            value = getattr(exc, attribute, None)
            if isinstance(value, int):
                return value

        response = getattr(exc, "response", None)
        if response is not None:
            for attribute in ("status_code", "status"):
                value = getattr(response, attribute, None)
                if isinstance(value, int):
                    return value

        return None

    @classmethod
    def _build_upstream_error(
        cls, exc: Exception, *, model: str, provider_stage: str
    ) -> ProviderUpstreamError:
        """Normalize Ollama client failures into a structured upstream error."""

        status_code = cls._extract_status_code(exc)
        retryable = status_code is not None and 500 <= status_code <= 599
        message = f"Ollama request failed during {provider_stage}: {exc}"
        if status_code is not None:
            message = (
                f"Ollama request failed during {provider_stage} "
                f"with upstream status {status_code}: {exc}"
            )

        logger.warning(
            "Ollama request failed model=%s stage=%s upstream_status=%s retryable=%s",
            model,
            provider_stage,
            status_code,
            retryable,
            exc_info=True,
        )
        return ProviderUpstreamError(
            message,
            provider_stage=provider_stage,
            upstream_status_code=status_code,
            retryable=retryable,
        )

    def _chat_json(
        self, model: str, system_prompt: str, user_prompt: str, provider_stage: str
    ) -> dict[str, Any]:
        """Send a chat request and parse the returned JSON object.

        Args:
            model: Ollama model name to use.
            system_prompt: System instruction describing the task and format.
            user_prompt: User-specific request content.

        Returns:
            dict[str, Any]: Parsed JSON payload returned by the model.

        Raises:
            LLMProviderError: If the Ollama request fails.
            ProviderResponseFormatError: If the response content is not JSON.
        """

        try:
            response = self.client.chat(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                format="json",
                stream=False,
            )
        except Exception as exc:
            raise self._build_upstream_error(
                exc,
                model=model,
                provider_stage=provider_stage,
            ) from exc

        logger.info(
            "Ollama request completed for model=%s stage=%s", model, provider_stage
        )
        return self._extract_json_payload(response)

    def interpret_action(self, participant_input: str) -> dict[str, Any]:
        """Interpret participant text via Ollama.

        Args:
            participant_input: Free-text participant action.

        Returns:
            dict[str, Any]: Raw payload intended for ``InterpretedAction``.

        Raises:
            LLMProviderError: If the Ollama request fails.
            ProviderResponseFormatError: If the model does not return JSON.
        """

        expected_shape = {
            "action_summary": "string",
            "action_types": [
                "containment|coordination|communication|escalation|analysis|recovery|monitoring|legal|business_continuity"
            ],
            "targets": ["string"],
            "intent": "string",
            "expected_effects": ["string"],
            "risks": ["string"],
            "uncertainties": ["string"],
            "priority": "low|medium|high",
            "confidence": "number between 0 and 1",
        }
        return self._chat_json(
            model=self.interpret_model,
            system_prompt=(
                f"{self.interpret_prompt}\n"
                "Return only a single JSON object and no surrounding prose.\n"
                f"Expected shape: {json.dumps(expected_shape, ensure_ascii=True)}"
            ),
            user_prompt=f"Deltagaratgard:\n{participant_input}",
            provider_stage="interpret_action",
        )

    def generate_narration(self, state: SessionState) -> dict[str, Any]:
        """Generate a narrated situation update via Ollama.

        Args:
            state: Session state after deterministic rules have been applied.

        Returns:
            dict[str, Any]: Raw payload intended for ``NarratorResponse``.

        Raises:
            LLMProviderError: If the Ollama request fails.
            ProviderResponseFormatError: If the model does not return JSON.
        """

        expected_shape = {
            "situation_update": "string",
            "key_points": ["string"],
            "new_consequences": ["string"],
            "injects": [
                {
                    "type": "media|executive|operations|technical|stakeholder",
                    "title": "string",
                    "message": "string",
                }
            ],
            "decisions_to_consider": ["string"],
            "facilitator_notes": "string",
        }
        return self._chat_json(
            model=self.narration_model,
            system_prompt=(
                f"{self.narration_prompt}\n"
                "Return only a single JSON object and no surrounding prose.\n"
                f"Expected shape: {json.dumps(expected_shape, ensure_ascii=True)}"
            ),
            user_prompt=f"Session state:\n{state.model_dump_json()}",
            provider_stage="generate_narration",
        )

    def generate_debrief(
        self, scenario: Scenario, state: SessionState, timeline: list[Turn]
    ) -> dict[str, Any]:
        """Generate a structured debrief from the finished session."""

        expected_shape = {
            "exercise_summary": "string",
            "timeline_summary": [
                {
                    "turn_number": "integer >= 1",
                    "summary": "string",
                    "outcome": "string",
                }
            ],
            "strengths": ["string"],
            "development_areas": ["string"],
            "debrief_questions": ["string"],
            "recommended_follow_ups": ["string"],
            "facilitator_notes": "string",
        }
        payload = {
            "scenario": scenario.model_dump(),
            "final_state": state.model_dump(),
            "timeline": [turn.model_dump() for turn in timeline],
        }
        return self._chat_json(
            model=self.narration_model,
            system_prompt=(
                f"{self.debrief_prompt}\n"
                "Return only a single JSON object and no surrounding prose.\n"
                f"Expected shape: {json.dumps(expected_shape, ensure_ascii=True)}"
            ),
            user_prompt=f"Ovningsunderlag:\n{json.dumps(payload, ensure_ascii=True)}",
            provider_stage="generate_debrief",
        )

    def generate_scenario_draft(
        self, source_text: str, source_format: str = "markdown"
    ) -> dict[str, Any]:
        """Generate a scenario draft from author-provided source text."""

        expected_shape = {
            "id": "string",
            "title": "string",
            "version": "string",
            "description": "string",
            "audiences": ["krisledning|it-ledning|kommunikation"],
            "training_goals": ["string"],
            "difficulty": "low|medium|high",
            "timebox_minutes": "integer",
            "background": {
                "organization_type": "string",
                "context": "string",
                "threat_actor": "string",
                "assumptions": ["string"],
            },
            "states": [
                {
                    "id": "string",
                    "phase": "string",
                    "title": "string",
                    "description": "string",
                }
            ],
            "actors": [{"id": "string", "name": "string", "role": "string"}],
            "inject_catalog": [
                {
                    "id": "string",
                    "type": "media|executive|operations|technical|stakeholder",
                    "title": "string",
                    "description": "string",
                    "trigger_conditions": ["string"],
                    "audience_relevance": ["krisledning|it-ledning|kommunikation"],
                    "severity": "integer 1-5",
                }
            ],
            "text_matchers": [
                {
                    "id": "string",
                    "field": "action.action_types|action.targets",
                    "match_type": "contains_any|contains_all",
                    "patterns": ["string"],
                    "value": "string",
                }
            ],
            "target_aliases": [
                {"id": "string", "canonical": "string", "aliases": ["string"]}
            ],
            "interpretation_hints": [
                {
                    "id": "string",
                    "when": {
                        "text_contains_any": ["string"],
                        "action_types_contains": [
                            "containment|coordination|communication|escalation|analysis|recovery|monitoring|legal|business_continuity"
                        ],
                        "targets_contains": ["string"],
                    },
                    "add_action_types": [
                        "containment|coordination|communication|escalation|analysis|recovery|monitoring|legal|business_continuity"
                    ],
                    "add_targets": ["string"],
                }
            ],
            "rules": [{"id": "string", "name": "string"}],
            "executable_rules": [
                {
                    "id": "string",
                    "name": "string",
                    "trigger": "session_started|turn_processed",
                    "conditions": [
                        {
                            "fact": "state.phase|state.no_communication_turns|state.metrics.impact_level|state.metrics.media_pressure|state.metrics.service_disruption|state.metrics.leadership_pressure|state.metrics.public_confusion|state.metrics.attack_surface|state.flags.executive_escalation|state.flags.external_comms_sent|state.flags.forensic_analysis_started|state.flags.external_access_restricted|session.turn_number|action.action_types|action.targets",
                            "operator": "equals|not_equals|gte|lte|contains|not_contains",
                            "value": "string|integer|boolean",
                        }
                    ],
                    "effects": [
                        {
                            "type": "set_phase|add_active_inject|resolve_inject|append_focus_item|append_consequence|increment_metric|set_flag|append_exercise_log"
                        }
                    ],
                    "priority": "low|medium|high",
                    "once": "boolean",
                }
            ],
            "presentation_guidelines": {
                "krisledning": {"focus": ["string"], "tone": "string"}
            },
        }
        return self._chat_json(
            model=self.scenario_model,
            system_prompt=(
                f"{self.scenario_authoring_prompt}\n"
                "Return only a single JSON object and no surrounding prose.\n"
                f"Expected shape: {json.dumps(expected_shape, ensure_ascii=True)}"
            ),
            user_prompt=(f"Kallformat: {source_format}\nKalltext:\n{source_text}"),
            provider_stage="generate_scenario_draft",
        )


class OpenAIProvider(LLMProvider):
    """Stub implementation for a future OpenAI-backed provider.

    The class currently loads prompt files but intentionally raises a
    configuration error when called because external integration is not yet
    implemented in this project.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """Create an OpenAI provider stub from config data.

        Args:
            config: Mapping from ``config.yaml`` under ``llm_provider.openai``.
                The values are currently stored for future use only.
        """

        self.interpret_prompt = load_prompt("interpret_action.txt")
        self.narration_prompt = load_prompt("generate_narration.txt")
        self.debrief_prompt = load_prompt("generate_debrief.txt")
        self.scenario_authoring_prompt = load_prompt("generate_scenario_draft.txt")
        self.config = config or {}
        logger.info("Initialized OpenAIProvider stub")

    def interpret_action(self, participant_input: str) -> dict[str, Any]:
        """Attempt to interpret an action with the OpenAI provider.

        Args:
            participant_input: Free-text participant action.

        Returns:
            dict[str, Any]: Never returns while the provider is stubbed.

        Raises:
            ProviderConfigurationError: Always, because the provider is not yet
                implemented.
        """

        raise ProviderConfigurationError("OpenAIProvider is not implemented yet")

    def generate_narration(self, state: SessionState) -> dict[str, Any]:
        """Attempt to generate narration with the OpenAI provider.

        Args:
            state: Session state to narrate.

        Returns:
            dict[str, Any]: Never returns while the provider is stubbed.

        Raises:
            ProviderConfigurationError: Always, because the provider is not yet
                implemented.
        """

        raise ProviderConfigurationError("OpenAIProvider is not implemented yet")

    def generate_debrief(
        self, scenario: Scenario, state: SessionState, timeline: list[Turn]
    ) -> dict[str, Any]:
        """Attempt to generate a debrief with the OpenAI provider."""

        raise ProviderConfigurationError("OpenAIProvider is not implemented yet")

    def generate_scenario_draft(
        self, source_text: str, source_format: str = "markdown"
    ) -> dict[str, Any]:
        """Attempt to generate a scenario draft with the OpenAI provider."""

        raise ProviderConfigurationError("OpenAIProvider is not implemented yet")


def get_llm_provider() -> LLMProvider:
    """Create the configured runtime provider instance.

    The provider is selected from ``config.yaml`` by reading
    ``llm_provider.provider`` and then the matching nested provider section.

    Returns:
        LLMProvider: Configured provider instance.

    Raises:
        ProviderConfigurationError: If the configured provider name is not
            supported.

    Notes:
        To add a new provider, extend this factory with a new branch and define
        a matching configuration block in ``config.yaml``.
    """

    llm_config = load_llm_config()
    provider_name = str(llm_config.get("provider") or "ollama").lower()

    if provider_name == "ollama":
        provider_config = llm_config.get("ollama")
        if not isinstance(provider_config, dict):
            logger.error(
                "Missing or invalid llm_provider.ollama section in config.yaml"
            )
            raise ProviderConfigurationError(
                "Missing or invalid llm_provider.ollama section in config.yaml"
            )
        logger.info("Selected LLM provider=ollama")
        return OllamaProvider(provider_config)

    if provider_name == "openai":
        provider_config = llm_config.get("openai")
        if provider_config is not None and not isinstance(provider_config, dict):
            logger.error("Invalid llm_provider.openai section in config.yaml")
            raise ProviderConfigurationError(
                "Invalid llm_provider.openai section in config.yaml"
            )
        logger.info("Selected LLM provider=openai")
        return OpenAIProvider(provider_config)

    logger.error("Unsupported LLM provider requested: %s", provider_name)
    raise ProviderConfigurationError(f"Unsupported LLM provider: {provider_name}")
