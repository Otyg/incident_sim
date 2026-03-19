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

"""Scenario-driven enrichment of interpreted participant actions."""

from dataclasses import dataclass, field

from src.logging_utils import get_logger
from src.models.scenario import InterpretationHint, Scenario, TargetAlias, TextMatcher
from src.schemas.interpreted_action import InterpretedAction


logger = get_logger(__name__)


@dataclass
class EnrichedActionResult:
    """Container for an enriched action and resulting audit messages."""

    action: InterpretedAction
    log_messages: list[str] = field(default_factory=list)


class ScenarioActionEnricher:
    """Complement LLM-interpreted actions with scenario-defined support."""

    @staticmethod
    def _append_unique(items: list[str], value: str) -> bool:
        if value in items:
            return False
        items.append(value)
        return True

    @staticmethod
    def _normalize(text: str) -> str:
        return text.casefold()

    def _matches_text(self, matcher: TextMatcher, normalized_text: str) -> bool:
        normalized_patterns = [
            self._normalize(pattern) for pattern in matcher.patterns if pattern.strip()
        ]
        if matcher.match_type == "contains_all":
            return all(pattern in normalized_text for pattern in normalized_patterns)
        return any(pattern in normalized_text for pattern in normalized_patterns)

    def _matches_alias(
        self,
        alias: TargetAlias,
        normalized_text: str,
        normalized_targets: list[tuple[str, str]],
    ) -> tuple[bool, str | None]:
        normalized_aliases = [
            self._normalize(item) for item in alias.aliases if item.strip()
        ]
        for original, normalized_target in normalized_targets:
            if normalized_target in normalized_aliases:
                return True, original
        canonical = self._normalize(alias.canonical)
        for normalized_alias in normalized_aliases:
            if normalized_alias == canonical:
                continue
            if normalized_alias in normalized_text:
                return True, normalized_alias
        return False, None

    def _hint_matches(
        self,
        hint: InterpretationHint,
        normalized_text: str,
        action: InterpretedAction,
    ) -> bool:
        if hint.when.text_contains_any:
            if not any(
                self._normalize(pattern) in normalized_text
                for pattern in hint.when.text_contains_any
            ):
                return False

        if hint.when.action_types_contains:
            if not all(
                action_type in action.action_types
                for action_type in hint.when.action_types_contains
            ):
                return False

        if hint.when.targets_contains:
            if not all(
                target in action.targets for target in hint.when.targets_contains
            ):
                return False

        return True

    def enrich(
        self,
        scenario: Scenario,
        participant_input: str,
        interpreted_action: InterpretedAction,
    ) -> EnrichedActionResult:
        """Apply scenario-defined text matchers and interpretation hints."""

        updated = interpreted_action.model_copy(deep=True)
        normalized_text = self._normalize(participant_input)
        normalized_targets = [
            (target, self._normalize(target)) for target in updated.targets if target.strip()
        ]
        log_messages: list[str] = []

        for alias in scenario.target_aliases:
            matched, source = self._matches_alias(alias, normalized_text, normalized_targets)
            if not matched:
                continue

            added = self._append_unique(updated.targets, alias.canonical)
            if added:
                log_messages.append(
                    f"Target normaliserad: {source} -> {alias.canonical} ({alias.id})"
                )
                logger.info(
                    "Scenario target alias matched alias_id=%s canonical=%s source=%s",
                    alias.id,
                    alias.canonical,
                    source,
                )

        for matcher in scenario.text_matchers:
            if not self._matches_text(matcher, normalized_text):
                continue

            if matcher.field == "action.action_types":
                added = self._append_unique(updated.action_types, matcher.value)
            else:
                added = self._append_unique(updated.targets, matcher.value)

            if added:
                log_messages.append(f"Textmatchning träffade: {matcher.id}")
                logger.info("Scenario text matcher matched matcher_id=%s", matcher.id)

        for hint in scenario.interpretation_hints:
            if not self._hint_matches(hint, normalized_text, updated):
                continue

            added_any = False
            for action_type in hint.add_action_types:
                added_any = (
                    self._append_unique(updated.action_types, action_type) or added_any
                )
            for target in hint.add_targets:
                added_any = self._append_unique(updated.targets, target) or added_any

            if added_any:
                log_messages.append(f"Interpretation hint använd: {hint.id}")
                logger.info("Scenario interpretation hint matched hint_id=%s", hint.id)

        return EnrichedActionResult(action=updated, log_messages=log_messages)
