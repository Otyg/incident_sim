"""Factory helpers for selecting the configured storage backend."""

from pathlib import Path
from typing import Any

import yaml

from src.storage.in_memory import InMemoryScenarioRepository, InMemorySessionRepository
from src.storage.tinydb_json import TinyDBScenarioRepository, TinyDBSessionRepository


CONFIG_PATH = Path(__file__).resolve().parents[2] / "config.yaml"


class StorageConfigurationError(Exception):
    """Raised when the storage backend configuration is missing or invalid."""

    pass


def load_storage_config(path: Path | None = None) -> dict[str, Any]:
    """Load the storage configuration section from ``config.yaml``.

    Args:
        path: Optional override path for the configuration file.

    Returns:
        dict[str, Any]: Storage backend configuration mapping.

    Raises:
        StorageConfigurationError: If configuration is missing or malformed.
    """

    config_path = path or CONFIG_PATH
    if not config_path.exists():
        raise StorageConfigurationError(f"Configuration file not found: {config_path}")

    try:
        with config_path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
    except yaml.YAMLError as exc:
        raise StorageConfigurationError(
            f"Invalid YAML configuration in {config_path}"
        ) from exc

    if not isinstance(data, dict):
        raise StorageConfigurationError(
            f"Configuration root must be a mapping in {config_path}"
        )

    storage_config = data.get("storage")
    if not isinstance(storage_config, dict):
        raise StorageConfigurationError(
            "Missing or invalid storage section in config.yaml"
        )

    return storage_config


def create_storage_repositories() -> tuple[object, object]:
    """Create scenario and session repositories from the configured backend.

    Returns:
        tuple[object, object]: Scenario repository and session repository.

    Raises:
        StorageConfigurationError: If the configured backend is unsupported.
    """

    storage_config = load_storage_config()
    backend = str(storage_config.get("backend") or "tinydb").lower()

    if backend == "in_memory":
        return InMemoryScenarioRepository(), InMemorySessionRepository()

    if backend == "tinydb":
        tinydb_config = storage_config.get("tinydb")
        if tinydb_config is not None and not isinstance(tinydb_config, dict):
            raise StorageConfigurationError(
                "Invalid storage.tinydb section in config.yaml"
            )

        db_path = None
        if isinstance(tinydb_config, dict) and tinydb_config.get("path"):
            db_path = Path(str(tinydb_config["path"]))

        return TinyDBScenarioRepository(db_path), TinyDBSessionRepository(db_path)

    raise StorageConfigurationError(f"Unsupported storage backend: {backend}")
