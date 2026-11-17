import os
import subprocess
import sys
from pathlib import Path


def test_importing_application_does_not_require_database_settings(
    tmp_path: Path,
) -> None:
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("POSTGRES_", "KAFKA_"))
    }
    environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import app.main
import app.billing.worker
import app.visits.outbox
from app.common.setting.config import get_settings
from app.common.database.session import get_database
assert get_settings.cache_info().currsize == 0
assert get_database.cache_info().currsize == 0
""",
        ],
        check=False,
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
