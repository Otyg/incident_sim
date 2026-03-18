from pathlib import Path

from src.logging_utils import configure_logging


def flush_handlers(logger) -> None:
    for handler in logger.handlers:
        handler.flush()


def write_config(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def test_default_logging_routes_info_to_stdout_and_warning_to_stderr(capsys, tmp_path):
    config_path = tmp_path / "config.yaml"
    write_config(config_path, "{}\n")

    logger = configure_logging(config_path)
    logger.info("default info message")
    logger.warning("default warning message")
    flush_handlers(logger)

    captured = capsys.readouterr()
    assert "default info message" in captured.out
    assert "default warning message" not in captured.out
    assert "default warning message" in captured.err


def test_file_logging_writes_all_levels_to_file_and_warnings_to_stderr(
    capsys, tmp_path
):
    config_path = tmp_path / "config.yaml"
    log_path = tmp_path / "logs" / "backend.log"
    write_config(
        config_path,
        ("logging:\n  file: logs/backend.log\n"),
    )

    logger = configure_logging(config_path)
    logger.info("file info message")
    logger.warning("file warning message")
    logger.error("file error message")
    flush_handlers(logger)

    captured = capsys.readouterr()
    content = log_path.read_text(encoding="utf-8")

    assert "file info message" in content
    assert "file warning message" in content
    assert "file error message" in content
    assert "file info message" not in captured.out
    assert "file warning message" in captured.err
    assert "file error message" in captured.err
