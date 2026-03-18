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

"""Deterministic session state transitions for participant actions.

The rules engine applies a small set of explicit rules to the current session
state based on an already interpreted participant action. It does not perform
LLM work; it only updates metrics, flags, consequences, logs and focus items.
"""

from copy import deepcopy

from src.models.session import ExerciseLogItem, ParticipantActionLog, SessionState
from src.schemas.interpreted_action import InterpretedAction


class RulesEngine:
    @staticmethod
    def _add_focus_item(state: SessionState, item: str) -> None:
        """Append a focus item only if it is not already present.

        Args:
            state: Session state being updated.
            item: Focus item text to preserve once in the list.

        Returns:
            None: The state object is mutated in place.
        """

        if item not in state.focus_items:
            state.focus_items.append(item)

    def apply(
        self, state: SessionState, interpreted_action: InterpretedAction, raw_input: str
    ) -> SessionState:
        """Apply deterministic rules to a session state.

        Args:
            state: Current session state before rule processing.
            interpreted_action: Structured action created by the provider layer.
            raw_input: Original participant input used for audit logging.

        Returns:
            SessionState: A copied and updated session state.
        """

        updated = deepcopy(state)
        updated.turn_number += 1

        updated.participant_actions.append(
            ParticipantActionLog(
                turn=updated.turn_number, summary=interpreted_action.action_summary
            )
        )
        updated.exercise_log.append(
            ExerciseLogItem(
                turn=updated.turn_number, type="participant_action", text=raw_input
            )
        )

        action_types = set(interpreted_action.action_types)
        targets = set(interpreted_action.targets)

        if "containment" in action_types and (
            "external_access" in targets or "vpn" in targets
        ):
            updated.metrics.attack_surface = max(0, updated.metrics.attack_surface - 1)
            updated.metrics.service_disruption += 1
            updated.flags.external_access_restricted = True
            updated.consequences.append(
                "Begränsad extern åtkomst minskar attackytan men påverkar externa tjänster."
            )
            self._add_focus_item(updated, "Hantera påverkan på externa tjänster.")
            updated.exercise_log.append(
                ExerciseLogItem(
                    turn=updated.turn_number,
                    type="system_consequence",
                    text="Extern attackyta minskar, men tjänstepåverkan ökar externt.",
                )
            )

        if "analysis" in action_types or "forensics" in targets:
            updated.flags.forensic_analysis_started = True

        if "escalation" in action_types or "executive_team" in targets:
            updated.flags.executive_escalation = True
            self._add_focus_item(updated, "Förbered ledningsbeslut och eskalering.")

        if "communication" in action_types:
            updated.flags.external_comms_sent = True
            updated.no_communication_turns = 0
            self._add_focus_item(updated, "Samordna fortsatt extern kommunikation.")
        else:
            updated.no_communication_turns += 1
            if updated.no_communication_turns >= 2:
                updated.metrics.media_pressure += 1
                updated.metrics.public_confusion += 1
                updated.consequences.append("Fördröjd kommunikation ökar medietrycket.")
                self._add_focus_item(updated, "Ta fram ett första externt budskap.")

        if (
            updated.metrics.service_disruption >= 2
            and "inject-ops-001" not in updated.active_injects
        ):
            updated.active_injects.append("inject-ops-001")

        if (
            updated.metrics.media_pressure >= 2
            and "inject-media-001" not in updated.active_injects
        ):
            updated.active_injects.append("inject-media-001")

        if updated.metrics.impact_level >= 3 and not updated.flags.executive_escalation:
            updated.metrics.leadership_pressure += 1

        return updated
