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

"""Simple in-memory repositories for scenarios, sessions and timelines.

The module keeps persistence intentionally minimal for local development and
tests. Data is stored per-process and is cleared whenever the process exits.
"""

from src.models.scenario import Scenario
from src.models.session import SessionState
from src.models.turn import Turn


class InMemoryScenarioRepository:
    """In-memory storage for validated scenarios."""

    def __init__(self) -> None:
        self._items: dict[str, Scenario] = {}

    def save(self, scenario: Scenario) -> Scenario:
        """Store or replace a scenario by its identifier.

        Args:
            scenario: Scenario instance to persist.

        Returns:
            Scenario: The stored scenario.
        """

        self._items[scenario.id] = scenario
        return scenario

    def get(self, scenario_id: str) -> Scenario | None:
        """Fetch a scenario by identifier.

        Args:
            scenario_id: Identifier of the stored scenario.

        Returns:
            Scenario | None: Stored scenario if present, otherwise ``None``.
        """

        return self._items.get(scenario_id)

    def list(self) -> list[Scenario]:
        """List all stored scenarios in stable identifier order.

        Returns:
            list[Scenario]: Stored scenarios sorted by identifier.
        """

        return [self._items[key] for key in sorted(self._items)]

    def clear(self) -> None:
        """Remove all stored scenarios.

        Returns:
            None: This method mutates repository state in place.
        """

        self._items.clear()


class InMemorySessionRepository:
    """In-memory storage for session state and turn timelines."""

    def __init__(self) -> None:
        self._items: dict[str, SessionState] = {}
        self._timelines: dict[str, list[Turn]] = {}

    def save(self, session: SessionState) -> SessionState:
        """Store or replace the latest state for a session.

        Args:
            session: Session state to persist.

        Returns:
            SessionState: The stored session state.
        """

        self._items[session.session_id] = session
        self._timelines.setdefault(session.session_id, [])
        return session

    def get(self, session_id: str) -> SessionState | None:
        """Fetch the latest session state by identifier.

        Args:
            session_id: Identifier of the stored session.

        Returns:
            SessionState | None: Stored state if present, otherwise ``None``.
        """

        return self._items.get(session_id)

    def append_turn(self, session_id: str, turn: Turn) -> Turn:
        """Append a turn to the session timeline.

        Args:
            session_id: Identifier of the session whose timeline is updated.
            turn: Turn object to append.

        Returns:
            Turn: The appended turn.
        """

        self._timelines.setdefault(session_id, []).append(turn)
        return turn

    def get_timeline(self, session_id: str) -> list[Turn]:
        """Read a copy of the stored timeline for a session.

        Args:
            session_id: Identifier of the session to inspect.

        Returns:
            list[Turn]: Timeline in insertion order.
        """

        return list(self._timelines.get(session_id, []))

    def count(self) -> int:
        """Count stored sessions.

        Returns:
            int: Number of stored session entries.
        """

        return len(self._items)

    def clear(self) -> None:
        """Remove all stored sessions and timelines.

        Returns:
            None: This method mutates repository state in place.
        """

        self._items.clear()
        self._timelines.clear()
