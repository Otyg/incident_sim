"""TinyDB-backed JSON repositories for scenarios, sessions and timelines."""

from pathlib import Path

from tinydb import Query, TinyDB

from src.models.scenario import Scenario
from src.models.session import SessionState
from src.models.turn import Turn


DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "incident_sim.json"


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
        payload = scenario.model_dump()
        self._table.upsert(payload, query.id == scenario.id)
        return scenario

    def get(self, scenario_id: str) -> Scenario | None:
        """Fetch a scenario by identifier."""

        query = Query()
        payload = self._table.get(query.id == scenario_id)
        return Scenario.model_validate(payload) if payload else None

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
        payload = session.model_dump()
        self._sessions.upsert(payload, query.session_id == session.session_id)
        return session

    def get(self, session_id: str) -> SessionState | None:
        """Fetch the latest session state by identifier."""

        query = Query()
        payload = self._sessions.get(query.session_id == session_id)
        return SessionState.model_validate(payload) if payload else None

    def append_turn(self, session_id: str, turn: Turn) -> Turn:
        """Append a turn to the session timeline."""

        payload = turn.model_dump()
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
