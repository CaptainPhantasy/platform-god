"""
Audit log indexing and search for Platform God.

Provides fast indexed querying of audit logs using SQLite.
"""

import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from pydantic import ValidationError

from .models import AuditEvent, AuditQuery


class AuditIndexer:
    """
    Audit log indexer with SQLite backend.

    Builds and maintains a searchable index of audit events.
    Supports full-text search, filtering, and efficient queries.
    """

    DEFAULT_INDEX_DIR = Path("var/audit")
    INDEX_FILENAME = "audit_index.db"

    # Index schema version - bump to force rebuild
    SCHEMA_VERSION = 1

    def __init__(self, index_dir: Path | None = None, index_name: str = "audit_index.db"):
        """
        Initialize the audit indexer.

        Args:
            index_dir: Directory for the index database
            index_name: Name of the index database file
        """
        self._index_dir = Path(index_dir) if index_dir else self.DEFAULT_INDEX_DIR
        self._index_dir.mkdir(parents=True, exist_ok=True)
        self._index_path = self._index_dir / index_name
        self._lock = threading.RLock()
        self._local = threading.local()

        # Initialize database schema
        self._init_db()

    @property
    def _conn(self) -> sqlite3.Connection:
        """Get thread-local database connection."""
        if not hasattr(self._local, "conn"):
            self._local.conn = self._get_connection()
        return self._local.conn

    def _get_connection(self) -> sqlite3.Connection:
        """Create a new database connection with optimal settings."""
        conn = sqlite3.connect(
            self._index_path,
            check_same_thread=False,
            isolation_level=None,  # Autocommit mode
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA page_size=4096")
        conn.execute("PRAGMA cache_size=-64000")  # 64MB cache
        return conn

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Cursor]:
        """Context manager for transactions."""
        cursor = self._conn.cursor()
        try:
            yield cursor
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    def _init_db(self) -> None:
        """Initialize database schema."""
        with self._transaction() as cur:
            # Check if we need to create schema
            cur.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='audit_meta'
            """
            )
            if cur.fetchone():
                # Check schema version
                cur.execute("SELECT version FROM audit_meta WHERE key = 'schema_version'")
                row = cur.fetchone()
                if row and row["version"] >= self.SCHEMA_VERSION:
                    return  # Schema up to date

            # Create schema
            self._create_schema(cur)

    def _create_schema(self, cur: sqlite3.Cursor) -> None:
        """Create the complete database schema."""
        # Metadata table
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """
        )

        # Main audit events table
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                timestamp TEXT NOT NULL,
                event_type TEXT NOT NULL,
                actor TEXT NOT NULL,
                action TEXT NOT NULL,
                target TEXT,
                result TEXT NOT NULL,
                severity TEXT NOT NULL,
                error_message TEXT,
                correlation_id TEXT,
                parent_event_id TEXT,
                run_id TEXT,
                metadata TEXT,
                checksum TEXT,
                indexed_at TEXT NOT NULL DEFAULT (datetime('now')),
                log_file TEXT NOT NULL,
                log_line INTEGER NOT NULL
            )
        """
        )

        # Full-text search virtual table
        cur.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS audit_fts USING fts5(
                event_id,
                action,
                target,
                metadata,
                content='audit_events',
                content_rowid='id'
            )
        """
        )

        # Triggers to keep FTS in sync
        cur.execute(
            """
            CREATE TRIGGER IF NOT EXISTS audit_ai AFTER INSERT ON audit_events BEGIN
                INSERT INTO audit_fts(rowid, event_id, action, target, metadata)
                VALUES (new.id, new.event_id, new.action, new.target, new.metadata);
            END
        """
        )

        cur.execute(
            """
            CREATE TRIGGER IF NOT EXISTS audit_ad AFTER DELETE ON audit_events BEGIN
                INSERT INTO audit_fts(audit_fts, rowid, event_id, action, target, metadata)
                VALUES ('delete', old.id, old.event_id, old.action, old.target, old.metadata);
            END
        """
        )

        # Indexes for common queries
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_audit_events_timestamp
            ON audit_events(timestamp)
        """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_audit_events_event_type
            ON audit_events(event_type)
        """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_audit_events_actor
            ON audit_events(actor)
        """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_audit_events_severity
            ON audit_events(severity)
        """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_audit_events_result
            ON audit_events(result)
        """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_audit_events_correlation_id
            ON audit_events(correlation_id)
        """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_audit_events_run_id
            ON audit_events(run_id)
        """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_audit_events_log_file
            ON audit_events(log_file)
        """
        )

        # Composite indexes
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_audit_events_timestamp_severity
            ON audit_events(timestamp, severity)
        """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_audit_events_actor_timestamp
            ON audit_events(actor, timestamp)
        """
        )

        # Store schema version
        cur.execute(
            """
            INSERT OR REPLACE INTO audit_meta (key, value, updated_at)
            VALUES ('schema_version', ?, datetime('now'))
        """,
            (str(self.SCHEMA_VERSION),),
        )

    def index_event(self, event: AuditEvent, log_file: str, log_line: int) -> bool:
        """
        Index a single audit event.

        Args:
            event: The audit event to index
            log_file: Source log file path
            log_line: Line number in log file

        Returns:
            True if indexed successfully, False otherwise
        """
        try:
            with self._transaction() as cur:
                # Check if already indexed
                cur.execute(
                    """
                    SELECT id FROM audit_events WHERE event_id = ?
                """,
                    (event.event_id,),
                )
                if cur.fetchone():
                    return True  # Already indexed

                # Insert event
                cur.execute(
                    """
                    INSERT INTO audit_events (
                        event_id, timestamp, event_type, actor, action, target,
                        result, severity, error_message, correlation_id,
                        parent_event_id, run_id, metadata, checksum,
                        log_file, log_line
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        event.event_id,
                        event.timestamp,
                        event.event_type.value,
                        event.actor,
                        event.action,
                        event.target,
                        event.result.value,
                        event.severity.value,
                        event.error_message,
                        event.correlation_id,
                        event.parent_event_id,
                        event.run_id,
                        json.dumps(event.metadata) if event.metadata else None,
                        event.checksum,
                        log_file,
                        log_line,
                    ),
                )
            return True

        except (sqlite3.Error, ValueError):
            return False

    def index_log_file(self, log_file: Path | str) -> dict[str, int]:
        """
        Index all events from a log file.

        Args:
            log_file: Path to the audit log file

        Returns:
            Dict with 'indexed', 'skipped', 'failed' counts
        """
        log_path = Path(log_file)
        if not log_path.exists():
            return {"indexed": 0, "skipped": 0, "failed": 0, "error": "File not found"}

        indexed = 0
        skipped = 0
        failed = 0

        try:
            with open(log_path, "r", encoding="utf-8") as f:
                for line_num, line in enumerate(f, start=1):
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        data = json.loads(line)
                        event = AuditEvent(**data)
                        if self.index_event(event, str(log_path), line_num):
                            indexed += 1
                        else:
                            skipped += 1
                    except (json.JSONDecodeError, ValidationError, ValueError):
                        failed += 1

        except (IOError, OSError) as e:
            return {"indexed": indexed, "skipped": skipped, "failed": failed, "error": str(e)}

        return {"indexed": indexed, "skipped": skipped, "failed": failed}

    def index_all_logs(self, audit_dir: Path | str | None = None) -> dict[str, Any]:
        """
        Index all audit log files in a directory.

        Args:
            audit_dir: Directory containing audit logs (default: same as index_dir)

        Returns:
            Summary dict with total stats and per-file breakdown
        """
        if audit_dir is None:
            audit_dir = self._index_dir
        else:
            audit_dir = Path(audit_dir)

        total_indexed = 0
        total_skipped = 0
        total_failed = 0
        files_processed: list[dict[str, Any]] = []

        for log_file in sorted(audit_dir.glob("audit_*.jsonl")):
            result = self.index_log_file(log_file)
            total_indexed += result.get("indexed", 0)
            total_skipped += result.get("skipped", 0)
            total_failed += result.get("failed", 0)

            files_processed.append(
                {
                    "file": str(log_file),
                    **result,
                }
            )

        return {
            "total_indexed": total_indexed,
            "total_skipped": total_skipped,
            "total_failed": total_failed,
            "files": files_processed,
        }

    def search(self, query: AuditQuery) -> list[AuditEvent]:
        """
        Search audit events by query criteria.

        Args:
            query: AuditQuery with filters and search parameters

        Returns:
            List of matching AuditEvent objects
        """
        # Build SQL query
        sql, params = self._build_query(query)

        # Execute query
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(sql, params)
            rows = cursor.fetchall()

        # Convert to AuditEvent objects
        events = []
        for row in rows:
            try:
                event = self._row_to_event(row)
                events.append(event)
            except (ValidationError, ValueError):
                continue

        return events

    def _build_query(self, query: AuditQuery) -> tuple[str, list[Any]]:
        """Build SQL query from AuditQuery."""
        conditions: list[str] = []
        params: list[Any] = []

        # Base query
        if query.search_query:
            # Full-text search
            base_sql = """
                SELECT ae.* FROM audit_events ae
                JOIN audit_fts fts ON ae.id = fts.rowid
                WHERE audit_fts MATCH ?
            """
            params.append(self._escape_fts(query.search_query))
        else:
            base_sql = "SELECT * FROM audit_events WHERE 1=1"

        # Time range
        if query.start_time:
            conditions.append("timestamp >= ?")
            params.append(query.start_time)
        if query.end_time:
            conditions.append("timestamp <= ?")
            params.append(query.end_time)

        # Event types
        if query.event_types:
            placeholders = ",".join("?" * len(query.event_types))
            conditions.append(f"event_type IN ({placeholders})")
            params.extend([et.value for et in query.event_types])

        # Actors
        if query.actors:
            placeholders = ",".join("?" * len(query.actors))
            conditions.append(f"actor IN ({placeholders})")
            params.extend(query.actors)

        # Targets
        if query.targets:
            target_conditions = []
            for target in query.targets:
                target_conditions.append("target LIKE ?")
                params.append(f"%{target}%")
            if target_conditions:
                conditions.append(f"({' OR '.join(target_conditions)})")

        # Severities
        if query.severities:
            placeholders = ",".join("?" * len(query.severities))
            conditions.append(f"severity IN ({placeholders})")
            params.extend([s.value for s in query.severities])

        # Results
        if query.results:
            placeholders = ",".join("?" * len(query.results))
            conditions.append(f"result IN ({placeholders})")
            params.extend([r.value for r in query.results])

        # Correlation ID
        if query.correlation_id:
            conditions.append("correlation_id = ?")
            params.append(query.correlation_id)

        # Run ID
        if query.run_id:
            conditions.append("run_id = ?")
            params.append(query.run_id)

        # Combine conditions
        if conditions:
            if query.search_query:
                sql = base_sql + " AND " + " AND ".join(conditions)
            else:
                sql = base_sql + " AND " + " AND ".join(conditions)
        else:
            sql = base_sql

        # Sorting
        order_dir = "DESC" if query.sort_order == "desc" else "ASC"
        sql += f" ORDER BY {self._sanitize_identifier(query.sort_by)} {order_dir}"

        # Pagination
        sql += f" LIMIT {query.limit} OFFSET {query.offset}"

        return sql, params

    def _escape_fts(self, query: str) -> str:
        """Escape query for FTS5 MATCH."""
        # Simple escaping - wrap terms in double quotes
        return f'"{query.replace(chr(34), chr(34) * 2)}"'

    def _sanitize_identifier(self, identifier: str) -> str:
        """Sanitize SQL identifier to prevent injection."""
        # Only allow alphanumeric and underscore
        if not identifier.replace("_", "").replace("-", "").isalnum():
            return "timestamp"  # Safe default
        return identifier

    def _row_to_event(self, row: sqlite3.Row) -> AuditEvent:
        """Convert database row to AuditEvent."""
        metadata = None
        if row["metadata"]:
            try:
                metadata = json.loads(row["metadata"])
            except json.JSONDecodeError:
                pass

        return AuditEvent(
            event_id=row["event_id"],
            timestamp=row["timestamp"],
            event_type=row["event_type"],
            actor=row["actor"],
            action=row["action"],
            target=row["target"],
            result=row["result"],
            severity=row["severity"],
            error_message=row["error_message"],
            correlation_id=row["correlation_id"],
            parent_event_id=row["parent_event_id"],
            run_id=row["run_id"],
            metadata=metadata or {},
            checksum=row["checksum"],
        )

    def count(self, query: AuditQuery) -> int:
        """
        Count events matching a query.

        Args:
            query: AuditQuery with filters

        Returns:
            Number of matching events
        """
        # Build count query
        sql, params = self._build_query(query)

        # Replace SELECT with SELECT COUNT
        count_sql = "SELECT COUNT(*) as count FROM (" + sql + ")"

        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(count_sql, params)
            row = cursor.fetchone()

        return row["count"] if row else 0

    def get_event(self, event_id: str) -> AuditEvent | None:
        """
        Retrieve a single event by ID.

        Args:
            event_id: The event identifier

        Returns:
            AuditEvent or None if not found
        """
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                SELECT * FROM audit_events WHERE event_id = ?
            """,
                (event_id,),
            )
            row = cursor.fetchone()

        if row:
            try:
                return self._row_to_event(row)
            except (ValidationError, ValueError):
                pass
        return None

    def get_related_events(
        self,
        correlation_id: str | None = None,
        run_id: str | None = None,
        parent_event_id: str | None = None,
    ) -> list[AuditEvent]:
        """
        Get events related by correlation ID, run ID, or parent.

        Args:
            correlation_id: Correlation ID to match
            run_id: Run ID to match
            parent_event_id: Parent event ID to match

        Returns:
            List of related AuditEvent objects
        """
        conditions: list[str] = []
        params: list[Any] = []

        if correlation_id:
            conditions.append("correlation_id = ?")
            params.append(correlation_id)
        if run_id:
            conditions.append("run_id = ?")
            params.append(run_id)
        if parent_event_id:
            conditions.append("parent_event_id = ?")
            params.append(parent_event_id)

        if not conditions:
            return []

        sql = f"SELECT * FROM audit_events WHERE {' OR '.join(conditions)} ORDER BY timestamp"

        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(sql, params)
            rows = cursor.fetchall()

        events = []
        for row in rows:
            try:
                event = self._row_to_event(row)
                events.append(event)
            except (ValidationError, ValueError):
                continue

        return events

    def get_stats(self) -> dict[str, Any]:
        """
        Get overall statistics about the audit index.

        Returns:
            Dict with total counts and breakdowns
        """
        with self._lock:
            cursor = self._conn.cursor()

            # Total events
            cursor.execute("SELECT COUNT(*) as count FROM audit_events")
            total = cursor.fetchone()["count"]

            # By event type
            cursor.execute(
                """
                SELECT event_type, COUNT(*) as count
                FROM audit_events
                GROUP BY event_type
                ORDER BY count DESC
            """
            )
            by_type = {row["event_type"]: row["count"] for row in cursor.fetchall()}

            # By severity
            cursor.execute(
                """
                SELECT severity, COUNT(*) as count
                FROM audit_events
                GROUP BY severity
                ORDER BY count DESC
            """
            )
            by_severity = {row["severity"]: row["count"] for row in cursor.fetchall()}

            # By actor
            cursor.execute(
                """
                SELECT actor, COUNT(*) as count
                FROM audit_events
                GROUP BY actor
                ORDER BY count DESC
                LIMIT 20
            """
            )
            by_actor = {row["actor"]: row["count"] for row in cursor.fetchall()}

            # Time range
            cursor.execute(
                """
                SELECT MIN(timestamp) as min_time, MAX(timestamp) as max_time
                FROM audit_events
            """
            )
            time_row = cursor.fetchone()
            time_range = (time_row["min_time"], time_row["max_time"]) if time_row else (None, None)

            # Index size
            cursor.execute("SELECT page_count * page_size as bytes FROM pragma_page_count(), pragma_page_size()")
            size_bytes = cursor.fetchone()["bytes"] if cursor.fetchone() else 0

        return {
            "total_events": total,
            "by_event_type": by_type,
            "by_severity": by_severity,
            "top_actors": by_actor,
            "time_range": time_range,
            "index_size_bytes": size_bytes,
        }

    def rebuild_index(self) -> dict[str, int]:
        """
        Rebuild the entire index from scratch.

        Returns:
            Dict with indexing stats
        """
        with self._lock:
            # Drop existing tables
            cursor = self._conn.cursor()
            cursor.execute("DROP TABLE IF EXISTS audit_events")
            cursor.execute("DROP TABLE IF EXISTS audit_fts")
            cursor.execute("DROP TABLE IF EXISTS audit_meta")
            self._conn.commit()

            # Recreate schema
            self._create_schema(cursor)
            self._conn.commit()

        # Re-index all logs
        return self.index_all_logs()

    def close(self) -> None:
        """Close the database connection."""
        if hasattr(self._local, "conn"):
            self._local.conn.close()
            delattr(self._local, "conn")

    def __enter__(self) -> "AuditIndexer":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.close()


# Global default indexer
_default_indexer: AuditIndexer | None = None
_default_lock = threading.Lock()


def get_default_indexer() -> AuditIndexer:
    """Get or create the default global audit indexer."""
    global _default_indexer

    with _default_lock:
        if _default_indexer is None:
            _default_indexer = AuditIndexer()
        return _default_indexer
