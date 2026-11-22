"""Non-interactive engine selection must never wait on hidden stdin."""

from __future__ import annotations

import pytest

from src.cli import input as cli_input


def test_explicit_installed_ollama_model_skips_picker(monkeypatch) -> None:
    monkeypatch.setattr(cli_input, "find_model_by_name", lambda name: None)
    checked: list[str] = []
    monkeypatch.setattr(cli_input, "ensure_ollama_and_model", lambda name: checked.append(name) or True)

    def fail_picker(*args, **kwargs):
        raise AssertionError("questionary picker must not open for an explicit model")

    monkeypatch.setattr(cli_input.questionary, "select", fail_picker)
    name, provider = cli_input.select_model(True, "qwen3-coder:30b")
    assert name == "qwen3-coder:30b"
    assert provider == "Ollama"
    assert checked == ["qwen3-coder:30b"]


def test_missing_ollama_model_exits_instead_of_prompting(monkeypatch) -> None:
    monkeypatch.setattr(cli_input, "find_model_by_name", lambda name: None)
    monkeypatch.setattr(cli_input, "ensure_ollama_and_model", lambda name: False)
    monkeypatch.setattr(cli_input, "_noninteractive", lambda: True)

    def fail_picker(*args, **kwargs):
        raise AssertionError("must not prompt without a terminal")

    monkeypatch.setattr(cli_input.questionary, "select", fail_picker)
    with pytest.raises(SystemExit) as exc:
        cli_input.select_model(True, "qwen3-coder:30b")
    assert exc.value.code == 1


def test_no_model_without_terminal_fails_fast(monkeypatch) -> None:
    monkeypatch.setattr(cli_input, "_noninteractive", lambda: True)
    with pytest.raises(SystemExit) as exc:
        cli_input.select_model(True, None)
    assert exc.value.code == 1


def test_no_analysts_without_terminal_fails_fast(monkeypatch) -> None:
    monkeypatch.setattr(cli_input, "_noninteractive", lambda: True)
    with pytest.raises(SystemExit) as exc:
        cli_input.select_analysts({})
    assert exc.value.code == 1
