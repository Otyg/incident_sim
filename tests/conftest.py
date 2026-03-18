import sys
from pathlib import Path

import pytest

from src.storage.in_memory import InMemoryScenarioRepository, InMemorySessionRepository

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def reset_in_memory_repositories():
    from src import api as api_module

    original_scenario_repository = api_module.scenario_repository
    original_session_repository = api_module.session_repository
    api_module.scenario_repository = InMemoryScenarioRepository()
    api_module.session_repository = InMemorySessionRepository()
    api_module.scenario_repository.clear()
    api_module.session_repository.clear()
    yield
    api_module.scenario_repository.clear()
    api_module.session_repository.clear()
    api_module.scenario_repository = original_scenario_repository
    api_module.session_repository = original_session_repository
