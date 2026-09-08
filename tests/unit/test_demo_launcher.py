"""Behavior checks for the resource-conscious demo launcher."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = PROJECT_ROOT / "scripts" / "run_demo.sh"


def _fake_uv(tmp_path: Path) -> tuple[Path, Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log_path = tmp_path / "uv-calls.log"
    fake_uv = bin_dir / "uv"
    fake_uv.write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s\\n' \"$*\" >> \"$UV_CALL_LOG\"\n"
        "if [[ \"$*\" == *\"python -c\"* && \"${UV_FAKE_READY:-0}\" != \"1\" ]]; then\n"
        "    exit 1\n"
        "fi\n"
        "exit 0\n"
    )
    fake_uv.chmod(0o755)
    return bin_dir, log_path


def _run_launcher(tmp_path: Path, *, ready: bool) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    bin_dir, log_path = _fake_uv(tmp_path)
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}:{env['PATH']}",
            "UV_CALL_LOG": str(log_path),
            "UV_FAKE_READY": "1" if ready else "0",
        }
    )
    result = subprocess.run(
        ["bash", str(LAUNCHER)],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    calls = log_path.read_text().splitlines()
    return result, calls


def test_launcher_skips_install_when_dependencies_are_ready(tmp_path: Path) -> None:
    result, calls = _run_launcher(tmp_path, ready=True)

    assert result.returncode == 0
    assert "skipping installation" in result.stdout
    assert not any(call.startswith("sync ") for call in calls)
    assert calls[-1] == "run --no-sync python -m ai_inference.demo"


def test_launcher_installs_once_when_dependency_check_fails(tmp_path: Path) -> None:
    result, calls = _run_launcher(tmp_path, ready=False)

    assert result.returncode == 0
    assert "Running the one-time installer" in result.stdout
    assert "significant CPU, disk, and memory" in result.stdout
    assert calls.count("sync --extra dev --extra test") == 1
    assert calls[-1] == "run --no-sync python -m ai_inference.demo"
