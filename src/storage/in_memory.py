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
