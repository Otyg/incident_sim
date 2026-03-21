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

"""Deterministic scenario rule execution from structured scenario JSON."""

from copy import deepcopy

from src.logging_utils import get_logger
from src.models.scenario import (
    ExecutableRule,
    Scenario,
    ScenarioRuleEffect,
    ScenarioStateDefinition,
)
from src.models.session import ExerciseLogItem, SessionState
from src.schemas.interpreted_action import InterpretedAction


logger = get_logger(__name__)
RULE_PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}


class ScenarioEngine:
    """Apply structured, deterministic rules from a scenario definition."""

    @staticmethod
    def get_defined_phases(scenario: Scenario) -> list[str]:
        """Return stable scenario phase ids derived from initial state and rules."""

        return [state.phase for state in scenario.states]

    @staticmethod
    def get_state_definition(
        scenario: Scenario, phase: str
    ) -> ScenarioStateDefinition | None:
        """Return the configured scenario state for a phase if it exists."""

        return next((state for state in scenario.states if state.phase == phase), None)

    @staticmethod
    def is_full_state_definition(state_definition: ScenarioStateDefinition) -> bool:
        """Return whether a scenario state is complete enough to act as a full state."""

        return (
            state_definition.time is not None
            and state_definition.impact_level is not None
            and state_definition.narration is not None
        )

    @staticmethod
    def apply_state_definition(
        state: SessionState, state_definition: ScenarioStateDefinition
    ) -> SessionState:
        """Overlay a scenario state definition onto a live session state.

        Only fields explicitly present in the scenario definition are applied so
        metadata-only states can safely omit optional keys.
        """

        updated = state.model_copy(deep=True)
        updated.phase = state_definition.phase

        if state_definition.time is not None:
            updated.current_time = state_definition.time
        if state_definition.known_facts is not None:
            updated.known_facts = list(state_definition.known_facts)
        if state_definition.unknowns is not None:
            updated.unknowns = list(state_definition.unknowns)
        if state_definition.affected_systems is not None:
            updated.affected_systems = list(state_definition.affected_systems)
        if state_definition.business_impact is not None:
            updated.business_impact = list(state_definition.business_impact)
        if state_definition.impact_level is not None:
            updated.metrics.impact_level = state_definition.impact_level

        return updated

    @staticmethod
    def _get_fact_value(
        state: SessionState, action: InterpretedAction | None, fact: str
    ) -> str | int | bool | list[str]:
        fact_map = {
            "state.phase": state.phase,
            "state.no_communication_turns": state.no_communication_turns,
            "state.metrics.impact_level": state.metrics.impact_level,
            "state.metrics.media_pressure": state.metrics.media_pressure,
            "state.metrics.service_disruption": state.metrics.service_disruption,
            "state.metrics.leadership_pressure": state.metrics.leadership_pressure,
            "state.metrics.public_confusion": state.metrics.public_confusion,
            "state.metrics.attack_surface": state.metrics.attack_surface,
            "state.flags.executive_escalation": state.flags.executive_escalation,
            "state.flags.external_comms_sent": state.flags.external_comms_sent,
            "state.flags.forensic_analysis_started": state.flags.forensic_analysis_started,
            "state.flags.external_access_restricted": state.flags.external_access_restricted,
            "session.turn_number": state.turn_number,
            "action.action_types": action.action_types if action else [],
            "action.targets": action.targets if action else [],
        }
        return fact_map[fact]

    @staticmethod
    def _matches_condition(
        left: str | int | bool | list[str], operator: str, right: str | int | bool
    ) -> bool:
        if operator == "equals":
            return left == right
        if operator == "not_equals":
            return left != right
        if operator == "gte":
            return isinstance(left, int) and isinstance(right, int) and left >= right
        if operator == "lte":
            return isinstance(left, int) and isinstance(right, int) and left <= right
        if operator == "contains":
            return isinstance(left, list) and right in left
        if operator == "not_contains":
            return isinstance(left, list) and right not in left
        return False

    @staticmethod
    def _append_unique(target: list[str], item: str) -> None:
        if item not in target:
            target.append(item)

    @staticmethod
    def _rule_already_applied(state: SessionState, rule_id: str) -> bool:
        return any(
            log_item.type == "scenario_rule_applied" and log_item.text == rule_id
            for log_item in state.exercise_log
        )

    @staticmethod
    def _apply_effect(
        scenario: Scenario,
        state: SessionState,
        rule: ExecutableRule,
        effect: ScenarioRuleEffect,
    ) -> str:
        if effect.type == "set_phase" and effect.phase:
            previous_phase = state.phase
            state.phase = effect.phase
            state.exercise_log.append(
                ExerciseLogItem(
                    turn=state.turn_number,
                    type="phase_change",
                    text=f"Fasbyte: {previous_phase} -> {effect.phase}",
                )
            )
            return f"phase={effect.phase}"

        if effect.type == "add_active_inject" and effect.inject_id:
            blocking_inject_id = scenario.resolve_blocking_inject(
                effect.inject_id, state.triggered_injects
            )
            if blocking_inject_id:
                state.exercise_log.append(
                    ExerciseLogItem(
                        turn=state.turn_number,
                        type="scenario_event",
                        text=(
                            "Inject blockerat av trigger-constraint: "
                            f"{effect.inject_id} (blockerat av {blocking_inject_id})"
                        ),
                    )
                )
                return f"blocked_inject={effect.inject_id}"

            if effect.inject_id not in state.active_injects:
                state.active_injects.append(effect.inject_id)
                state.exercise_log.append(
                    ExerciseLogItem(
                        turn=state.turn_number,
                        type="scenario_event",
                        text=f"Inject aktiverat: {effect.inject_id}",
                    )
                )
            ScenarioEngine._append_unique(state.triggered_injects, effect.inject_id)
            return f"active_inject={effect.inject_id}"

        if effect.type == "resolve_inject" and effect.inject_id:
            if effect.inject_id in state.active_injects:
                state.active_injects.remove(effect.inject_id)
            self = ScenarioEngine
            self._append_unique(state.resolved_injects, effect.inject_id)
            state.exercise_log.append(
                ExerciseLogItem(
                    turn=state.turn_number,
                    type="scenario_event",
                    text=f"Inject löst: {effect.inject_id}",
                )
            )
            return f"resolved_inject={effect.inject_id}"

        if effect.type == "append_focus_item" and effect.item:
            ScenarioEngine._append_unique(state.focus_items, effect.item)
            return f"focus_item={effect.item}"

        if effect.type == "append_consequence" and effect.item:
            state.consequences.append(effect.item)
            return f"consequence={effect.item}"

        if (
            effect.type == "increment_metric"
            and effect.metric
            and effect.amount is not None
        ):
            metric_name = effect.metric.removeprefix("state.metrics.")
            current_value = getattr(state.metrics, metric_name)
            if metric_name == "impact_level":
                new_value = min(5, max(1, current_value + effect.amount))
            else:
                new_value = max(0, current_value + effect.amount)
            setattr(state.metrics, metric_name, new_value)
            return f"{metric_name}={new_value}"

        if effect.type == "set_flag" and effect.flag and effect.value is not None:
            flag_name = effect.flag.removeprefix("state.flags.")
            setattr(state.flags, flag_name, effect.value)
            return f"{flag_name}={effect.value}"

        if effect.type == "append_exercise_log" and effect.message:
            state.exercise_log.append(
                ExerciseLogItem(
                    turn=state.turn_number,
                    type=effect.log_type or "scenario_event",
                    text=effect.message,
                )
            )
            return f"log={effect.message}"

        logger.warning(
            "Skipped incomplete scenario effect rule_id=%s effect_type=%s",
            rule.id,
            effect.type,
        )
        return f"skipped={effect.type}"

    def apply(
        self,
        scenario: Scenario,
        state: SessionState,
        trigger: str,
        action: InterpretedAction | None = None,
    ) -> SessionState:
        """Apply matching executable rules for the given trigger."""

        updated = deepcopy(state)
        ordered_rules = sorted(
            enumerate(scenario.executable_rules),
            key=lambda item: (RULE_PRIORITY_ORDER[item[1].priority], item[0]),
        )

        for _, rule in ordered_rules:
            if rule.trigger != trigger:
                continue
            if rule.once and self._rule_already_applied(updated, rule.id):
                continue

            if not all(
                self._matches_condition(
                    self._get_fact_value(updated, action, condition.fact),
                    condition.operator,
                    condition.value,
                )
                for condition in rule.conditions
            ):
                continue

            applied_effects = [
                self._apply_effect(scenario, updated, rule, effect)
                for effect in rule.effects
            ]
            updated.exercise_log.append(
                ExerciseLogItem(
                    turn=updated.turn_number,
                    type="scenario_event",
                    text=f"Regel triggad: {rule.id} ({rule.name})",
                )
            )
            updated.exercise_log.append(
                ExerciseLogItem(
                    turn=updated.turn_number,
                    type="scenario_rule_applied",
                    text=rule.id,
                )
            )
            logger.info(
                "Applied scenario rule session_id=%s rule_id=%s trigger=%s effects=%s",
                updated.session_id,
                rule.id,
                trigger,
                applied_effects,
            )

        return updated
