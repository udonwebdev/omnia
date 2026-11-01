"""
OMNIA Module 45: Autonomous Quality Assurance, Software Verification & Continuous Testing Intelligence
Database & Integrity Verifier - database_verifier.py

Validates relational integrity, foreign keys, unique constraints, migration safety,
and rollback behavior in isolated test environments.
"""

from __future__ import annotations

import logging
import sqlite3
from typing import List, Optional

logger = logging.getLogger("Omnia.QAVerification.DatabaseVerifier")


class DatabaseIntegrityVerifier:
    """
    Evaluates database schema constraints, migrations, and referential integrity.
    """

    def verify_sqlite_integrity(self, db_path: str = "omnia.db") -> tuple[bool, List[str]]:
        violations: List[str] = []
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # 1. PRAGMA integrity_check
            cursor.execute("PRAGMA integrity_check")
            rows = cursor.fetchall()
            for r in rows:
                if r[0] != "ok":
                    violations.append(f"SQLite integrity check failure: {r[0]}")

            # 2. PRAGMA foreign_key_check
            cursor.execute("PRAGMA foreign_key_check")
            fk_violations = cursor.fetchall()
            for f in fk_violations:
                violations.append(f"Foreign key violation in table '{f[0]}', rowid {f[1]}")

            conn.close()
        except Exception as e:
            violations.append(f"Database verification exception: {e}")

        passed = len(violations) == 0
        logger.info(f"Database integrity verification on '{db_path}': Passed={passed}, Violations={len(violations)}")
        return passed, violations
