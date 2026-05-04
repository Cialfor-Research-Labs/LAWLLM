"""
Database Client (Read-Only)
============================
Placeholder for optional read-only database access.
Currently all data is served from trained_data.json.

If a database is needed in the future, configure it here.
This client must remain READ-ONLY — no writes, no mutations.
"""

import logging
from typing import Optional

logger = logging.getLogger("tllac.db")


class DBClient:
    """
    Read-only database client.

    Future options:
      - SQLite (local, file-based)
      - PostgreSQL (via asyncpg, read-only credentials)
    """

    def __init__(self, db_url: Optional[str] = None):
        self._db_url = db_url
        self._connection = None
        logger.info(
            "DBClient initialized (db_url=%s).",
            db_url or "None — using trained_data.json only",
        )

    def get_connection(self):
        """Return a database connection (None if no DB configured)."""
        return self._connection

    def is_connected(self) -> bool:
        """Check whether a database connection is active."""
        return self._connection is not None


# Singleton instance
db_client = DBClient()
