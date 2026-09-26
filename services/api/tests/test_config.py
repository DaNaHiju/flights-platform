"""Fail-fast config: the API must name EVERY missing variable in one error."""

import os
import subprocess
import sys
from pathlib import Path

SERVICE_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = SERVICE_DIR.parents[1]


def test_missing_env_names_every_variable_in_one_error():
    # A fresh interpreter: in this process app.config was already imported with
    # the variables set by conftest.py, so it can't be re-checked here.
    env = {k: v for k, v in os.environ.items() if k not in ("REDIS_URL", "DATABASE_URL")}
    env["PYTHONPATH"] = os.pathsep.join([str(REPO_ROOT), str(SERVICE_DIR)])

    result = subprocess.run(
        [sys.executable, "-c", "import app.main"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    error_line = result.stderr.strip().splitlines()[-1]
    assert error_line.startswith("RuntimeError: Missing required environment variable(s)")
    assert "REDIS_URL" in error_line
    assert "DATABASE_URL" in error_line
