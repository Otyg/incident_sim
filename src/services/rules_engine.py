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
from datetime import datetime, timedelta

from src.models.scenario import Scenario
from src.models.session import ExerciseLogItem, ParticipantActionLog, SessionState
from src.schemas.interpreted_action import InterpretedAction
from src.services.scenario_engine import ScenarioEngine


class RulesEngine:
    def __init__(self) -> None:
        self.scenario_engine = ScenarioEngine()

    @staticmethod
    def _advance_time(current_time: str, minutes: int = 15) -> str:
        """Advance a HH:MM timestamp by a fixed number of minutes."""

        try:
            parsed = datetime.strptime(current_time, "%H:%M")
        except ValueError:
            return current_time

        return (parsed + timedelta(minutes=minutes)).strftime("%H:%M")

    def apply(
        self,
        scenario: Scenario,
        state: SessionState,
        interpreted_action: InterpretedAction,
        raw_input: str,
        interpretation_log_messages: list[str] | None = None,
    ) -> SessionState:
        """Apply deterministic rules to a session state.

        Args:
            scenario: Scenario definition containing executable rules.
            state: Current session state before rule processing.
            interpreted_action: Structured action created by the provider layer.
            raw_input: Original participant input used for audit logging.

        Returns:
            SessionState: A copied and updated session state.
        """

        updated = deepcopy(state)
        updated.turn_number += 1
        updated.current_time = self._advance_time(updated.current_time)

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
        for message in interpretation_log_messages or []:
            updated.exercise_log.append(
                ExerciseLogItem(
                    turn=updated.turn_number,
                    type="interpretation_support",
                    text=message,
                )
            )

        if "communication" in interpreted_action.action_types:
            updated.flags.external_comms_sent = True
            updated.no_communication_turns = 0
        else:
            updated.no_communication_turns += 1

        return self.scenario_engine.apply(
            scenario=scenario,
            state=updated,
            trigger="turn_processed",
            action=interpreted_action,
        )
