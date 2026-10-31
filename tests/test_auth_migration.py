"""Check that the account migration preserves existing schedule data."""

import os
import sqlite3
import subprocess
import sys
from pathlib import Path


def test_upgrade_keeps_existing_groups(tmp_path: Path) -> None:
    database = tmp_path / "schedule.sqlite"
    environment = os.environ.copy()
    environment["DATABASE_URL"] = f"sqlite+aiosqlite:///{database}"
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "e7f8a9b0c1d2"],
        env=environment,
        check=True,
        capture_output=True,
    )
    with sqlite3.connect(database) as connection:
        query = "INSERT INTO groups VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        # The table's column order comes from the existing groups migration.
        connection.execute(
            query,
            ("existing", "F", 1, 20, True, 1),
        )
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        env=environment,
        check=True,
        capture_output=True,
    )
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT name FROM groups").fetchall() == [("existing",)]
        names = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        assert ("users",) in names
        assert ("login_sessions",) in names
