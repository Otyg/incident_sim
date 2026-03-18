from pathlib import Path

import pytest

from src.storage.factory import StorageConfigurationError, load_storage_config


def test_load_storage_config_reads_dist_when_default_config_is_missing(monkeypatch):
    dist_path = Path("/virtual/config.yaml.dist")
    monkeypatch.setattr("src.storage.factory.CONFIG_PATH", Path("/virtual/config.yaml"))
    monkeypatch.setattr("src.storage.factory.DIST_CONFIG_PATH", dist_path)

    def fake_exists(self: Path) -> bool:
        return self == dist_path

    def fake_open(self: Path, *args, **kwargs):
        if self == dist_path:
            return open("/home/maves/projects/incident_sim/config.yaml.dist", *args, **kwargs)
        raise FileNotFoundError(self)

    monkeypatch.setattr(Path, "exists", fake_exists)
    monkeypatch.setattr(Path, "open", fake_open)

    storage_config = load_storage_config()

    assert storage_config["backend"] == "tinydb"


def test_load_storage_config_logs_warning_when_falling_back_to_dist(
    monkeypatch
):
    dist_path = Path("/virtual/config.yaml.dist")
    missing_config_path = Path("/virtual/config.yaml")
    monkeypatch.setattr("src.storage.factory.CONFIG_PATH", missing_config_path)
    monkeypatch.setattr("src.storage.factory.DIST_CONFIG_PATH", dist_path)
    warning_calls = []

    def fake_exists(self: Path) -> bool:
        return self == dist_path

    def fake_open(self: Path, *args, **kwargs):
        if self == dist_path:
            return open("/home/maves/projects/incident_sim/config.yaml.dist", *args, **kwargs)
        raise FileNotFoundError(self)

    def fake_warning(message, *args):
        warning_calls.append(message % args)

    monkeypatch.setattr(Path, "exists", fake_exists)
    monkeypatch.setattr(Path, "open", fake_open)
    monkeypatch.setattr("src.storage.factory.logger.warning", fake_warning)

    load_storage_config()

    assert warning_calls == [
        f"Storage configuration file was not found at {missing_config_path}, "
        f"falling back to {dist_path}"
    ]


def test_load_storage_config_raises_when_explicit_path_is_missing(tmp_path):
    missing_path = tmp_path / "missing.yaml"

    with pytest.raises(StorageConfigurationError):
        load_storage_config(missing_path)
