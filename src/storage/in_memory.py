from src.models.scenario import Scenario
from src.models.session import SessionState
from src.models.turn import Turn


class InMemoryScenarioRepository:
    def __init__(self) -> None:
        self._items: dict[str, Scenario] = {}

    def save(self, scenario: Scenario) -> Scenario:
        self._items[scenario.id] = scenario
        return scenario

    def get(self, scenario_id: str) -> Scenario | None:
        return self._items.get(scenario_id)

    def clear(self) -> None:
        self._items.clear()


class InMemorySessionRepository:
    def __init__(self) -> None:
        self._items: dict[str, SessionState] = {}
        self._timelines: dict[str, list[Turn]] = {}

    def save(self, session: SessionState) -> SessionState:
        self._items[session.session_id] = session
        self._timelines.setdefault(session.session_id, [])
        return session

    def get(self, session_id: str) -> SessionState | None:
        return self._items.get(session_id)

    def append_turn(self, session_id: str, turn: Turn) -> Turn:
        self._timelines.setdefault(session_id, []).append(turn)
        return turn

    def get_timeline(self, session_id: str) -> list[Turn]:
        return list(self._timelines.get(session_id, []))

    def count(self) -> int:
        return len(self._items)

    def clear(self) -> None:
        self._items.clear()
        self._timelines.clear()
