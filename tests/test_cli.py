from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from lebench.cli import main


def test_version(capsys):
    with pytest.raises(SystemExit) as ei:
        main(["--version"])
    assert ei.value.code == 0
    out = capsys.readouterr().out
    assert "LeBench" in out


def test_profiles(capsys):
    assert main(["profiles"]) == 0
    out = capsys.readouterr().out
    assert "bare_metal" in out
    assert "vps" in out


def test_modules(capsys):
    assert main(["modules"]) == 0
    out = capsys.readouterr().out
    assert "system" in out


def test_doctor(capsys):
    assert main(["doctor"]) == 0
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["tool"]["name"] == "LeBench"
    assert "system" in data["modules"]


def test_run_quick_dry_run(tmp_path, capsys):
    code = main(
        [
            "run",
            "--profile",
            "vps",
            "--intensity",
            "quick",
            "--dry-run",
            "--output-dir",
            str(tmp_path),
        ]
    )
    assert code == 0
    files = list(tmp_path.glob("*.internal.json"))
    assert files
    data = json.loads(files[0].read_text(encoding="utf-8"))
    assert data["internal_format"] == "lebench-internal-v0"
    assert "notice" in data
    assert "system" in data["modules"]


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="full run targets Linux")
def test_run_quick_system(tmp_path):
    code = main(
        [
            "run",
            "--profile",
            "vps",
            "--intensity",
            "quick",
            "--modules",
            "system",
            "--output-dir",
            str(tmp_path),
        ]
    )
    assert code == 0
    txts = list(Path(tmp_path).glob("*.txt"))
    assert txts
    text = txts[0].read_text(encoding="utf-8")
    assert "system" in text
    assert "LeBench" in text
