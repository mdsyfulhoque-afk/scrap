"""Database migration runner with ledger tracking."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

from data_fetcher.database import Database, DatabaseError

logger = logging.getLogger(__name__)


class MigrationRunner:
    """Runs database migrations with ledger tracking."""

    def __init__(self, db: Database, migrations_dir: str | Path) -> None:
        self.db = db
        self.migrations_dir = Path(migrations_dir)

    def _get_applied(self) -> set[str]:
        """Return set of applied migration versions."""
        try:
            with self.db.connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT version FROM schema_migrations")
                    return {row[0] for row in cur.fetchall()}
        except Exception as e:
            logger.warning(f"Could not read migration ledger: {e}")
            return set()

    def _file_checksum(self, filepath: Path) -> str:
        """Compute SHA-256 checksum of migration file."""
        content = filepath.read_text(encoding="utf-8")
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def apply(self, migration_file: Path) -> bool:
        """Apply a single migration if not already applied."""
        version = migration_file.stem
        applied = self._get_applied()

        if version in applied:
            logger.debug(f"Migration {version} already applied, skipping")
            return True

        checksum = self._file_checksum(migration_file)
        sql = migration_file.read_text(encoding="utf-8")

        try:
            with self.db.connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql)
                    cur.execute(
                        "INSERT INTO schema_migrations (version, checksum) VALUES (%s, %s)",
                        (version, checksum),
                    )
                conn.commit()
            logger.info(f"Applied migration: {version}")
            return True
        except Exception as e:
            logger.error(f"Failed to apply migration {version}: {e}")
            return False

    def run_all(self) -> tuple[int, int]:
        """Apply all pending migrations in order.

        Returns:
            (applied_count, skipped_count)
        """
        if not self.migrations_dir.exists():
            logger.warning(f"Migrations directory not found: {self.migrations_dir}")
            return 0, 0

        migration_files = sorted(self.migrations_dir.glob("*.sql"))
        applied = 0
        skipped = 0

        for migration_file in migration_files:
            version = migration_file.stem
            if version in self._get_applied():
                skipped += 1
                continue
            if self.apply(migration_file):
                applied += 1

        logger.info(f"Migrations complete: {applied} applied, {skipped} skipped")
        return applied, skipped
