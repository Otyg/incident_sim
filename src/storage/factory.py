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

"""Factory helpers for selecting the configured storage backend."""

from pathlib import Path
from typing import Any

import yaml

from src.logging_utils import get_logger
from src.storage.in_memory import InMemoryScenarioRepository, InMemorySessionRepository
from src.storage.buffered import BufferedSessionRepository
from src.storage.tinydb_json import (
    DEFAULT_DB_PATH,
    TinyDBScenarioRepository,
    TinyDBSessionRepository,
)


CONFIG_PATH = Path(__file__).resolve().parents[2] / "config.yaml"
DIST_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config.yaml.dist"
logger = get_logger(__name__)


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
        fallback_path = None
        if path is None and DIST_CONFIG_PATH.exists():
            fallback_path = DIST_CONFIG_PATH

        if not fallback_path:
            logger.error("Storage configuration file was not found: %s", config_path)
            raise StorageConfigurationError(
                f"Configuration file not found: {config_path}"
            )

        logger.warning(
            "Storage configuration file was not found at %s, falling back to %s",
            config_path,
            fallback_path,
        )
        config_path = fallback_path

    try:
        with config_path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
    except yaml.YAMLError as exc:
        logger.error(
            "Failed to parse storage configuration from %s",
            config_path,
            exc_info=True,
        )
        raise StorageConfigurationError(
            f"Invalid YAML configuration in {config_path}"
        ) from exc

    if not isinstance(data, dict):
        logger.error("Storage configuration root was not a mapping in %s", config_path)
        raise StorageConfigurationError(
            f"Configuration root must be a mapping in {config_path}"
        )

    storage_config = data.get("storage")
    if not isinstance(storage_config, dict):
        logger.error("Missing or invalid storage section in %s", config_path)
        raise StorageConfigurationError(
            "Missing or invalid storage section in config.yaml"
        )

    logger.info("Loaded storage configuration from %s", config_path)
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
        logger.info("Initializing storage repositories with backend=in_memory")
        return InMemoryScenarioRepository(), InMemorySessionRepository()

    if backend == "tinydb":
        tinydb_config = storage_config.get("tinydb")
        if tinydb_config is not None and not isinstance(tinydb_config, dict):
            logger.error("Invalid storage.tinydb section in config.yaml")
            raise StorageConfigurationError(
                "Invalid storage.tinydb section in config.yaml"
            )

        db_path = None
        if isinstance(tinydb_config, dict) and tinydb_config.get("path"):
            db_path = Path(str(tinydb_config["path"]))

        logger.info(
            "Initializing storage repositories with backend=tinydb path=%s",
            db_path or DEFAULT_DB_PATH,
        )
        return (
            TinyDBScenarioRepository(db_path),
            BufferedSessionRepository(
                active_repo=InMemorySessionRepository(),
                archive_repo=TinyDBSessionRepository(db_path),
            ),
        )

    logger.error("Unsupported storage backend requested: %s", backend)
    raise StorageConfigurationError(f"Unsupported storage backend: {backend}")
