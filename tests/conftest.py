import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def reset_in_memory_repositories():
    from src.api import scenario_repository, session_repository

    scenario_repository.clear()
    session_repository.clear()
    yield
    scenario_repository.clear()
    session_repository.clear()
