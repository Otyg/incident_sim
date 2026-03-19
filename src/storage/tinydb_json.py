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

"""TinyDB-backed JSON repositories for scenarios, sessions and timelines."""

from pathlib import Path
from typing import Any

from tinydb import Query, TinyDB

from src.models.scenario import Scenario
from src.models.session import SessionState
from src.models.turn import Turn


DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "incident_sim.json"


def _drop_none_values(value: Any) -> Any:
    """Recursively remove ``None`` values from dict payloads.

    This keeps TinyDB persistence aligned with the checked-in JSON Schema for
    discriminated effect objects and also lets us read older rows that were
    stored before `exclude_none` handling was added.
    """

    if isinstance(value, dict):
        return {
            key: _drop_none_values(item)
            for key, item in value.items()
            if item is not None
        }
    if isinstance(value, list):
        return [_drop_none_values(item) for item in value]
    return value


class TinyDBScenarioRepository:
    """JSON-backed storage for validated scenarios using TinyDB."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = TinyDB(self.db_path)
        self._table = self._db.table("scenarios")

    def save(self, scenario: Scenario) -> Scenario:
        """Store or replace a scenario by identifier."""

        query = Query()
        payload = _drop_none_values(scenario.model_dump(exclude_none=True))
        self._table.upsert(payload, query.id == scenario.id)
        return scenario

    def get(self, scenario_id: str) -> Scenario | None:
        """Fetch a scenario by identifier."""

        query = Query()
        payload = self._table.get(query.id == scenario_id)
        return Scenario.model_validate(_drop_none_values(payload)) if payload else None

    def list(self) -> list[Scenario]:
        """List all stored scenarios in stable identifier order."""

        rows = sorted(self._table.all(), key=lambda item: item["id"])
        return [Scenario.model_validate(_drop_none_values(row)) for row in rows]

    def clear(self) -> None:
        """Remove all stored scenarios."""

        self._table.truncate()


class TinyDBSessionRepository:
    """JSON-backed storage for session state and turn timelines using TinyDB."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = TinyDB(self.db_path)
        self._sessions = self._db.table("sessions")
        self._timeline = self._db.table("timeline")

    def save(self, session: SessionState) -> SessionState:
        """Store or replace the latest state for a session."""

        query = Query()
        payload = _drop_none_values(session.model_dump(exclude_none=True))
        self._sessions.upsert(payload, query.session_id == session.session_id)
        return session

    def get(self, session_id: str) -> SessionState | None:
        """Fetch the latest session state by identifier."""

        query = Query()
        payload = self._sessions.get(query.session_id == session_id)
        return SessionState.model_validate(payload) if payload else None

    def append_turn(self, session_id: str, turn: Turn) -> Turn:
        """Append a turn to the session timeline."""

        payload = _drop_none_values(turn.model_dump(exclude_none=True))
        payload["session_id"] = session_id
        self._timeline.insert(payload)
        return turn

    def get_timeline(self, session_id: str) -> list[Turn]:
        """Read the stored timeline for a session in turn order."""

        query = Query()
        rows = self._timeline.search(query.session_id == session_id)
        ordered = sorted(rows, key=lambda item: item["turn_number"])
        return [
            Turn.model_validate({k: v for k, v in row.items() if k != "session_id"})
            for row in ordered
        ]

    def count(self) -> int:
        """Count stored sessions."""

        return len(self._sessions)

    def clear(self) -> None:
        """Remove all stored sessions and timeline events."""

        self._sessions.truncate()
        self._timeline.truncate()
