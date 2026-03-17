from src.models.scenario import Scenario
from src.models.session import SessionState


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

    def save(self, session: SessionState) -> SessionState:
        self._items[session.session_id] = session
        return session

    def get(self, session_id: str) -> SessionState | None:
        return self._items.get(session_id)

    def count(self) -> int:
        return len(self._items)

    def clear(self) -> None:
        self._items.clear()
