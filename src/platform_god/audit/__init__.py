"""
Platform God Audit Module.

Comprehensive audit logging, indexing, and reporting for compliance and forensics.

Features:
- Thread-safe, async-capable audit logging to JSONL files
- SQLite-backed indexing with full-text search
- Report generation with export to CSV/JSON
- Immutable, append-only log storage
- Support for concurrent writes

Usage:
    >>> from platform_god.audit import AuditLogger, AuditEvent
    >>>
    >>> logger = AuditLogger()
    >>> event = AuditEvent(
    ...     action="User logged in",
    ...     actor="user@example.com",
    ...     event_type=AuditEventType.AUTH_SUCCESS
    ... )
    >>> logger.log(event)

Querying:
    >>> from platform_god.audit import AuditIndexer, AuditQuery
    >>>
    >>> indexer = AuditIndexer()
    >>> indexer.index_all_logs()  # Build index
    >>>
    >>> query = AuditQuery(
    ...     start_time="2024-01-01T00:00:00Z",
    ...     severities=[AuditLevel.ERROR, AuditLevel.CRITICAL]
    ... )
    >>> events = indexer.search(query)

Reporting:
    >>> from platform_god.audit import AuditReporter
    >>>
    >>> reporter = AuditReporter()
    >>> report = reporter.generate_summary_report()
    >>> reporter.export_csv(report, "audit_report.csv")
"""

from .index import (
    AuditIndexer,
    get_default_indexer,
)
from .logger import (
    AuditLogger,
    WriteMode,
    get_default_logger,
    log_critical,
    log_error,
    log_event,
    log_info,
    log_warning,
)
from .models import (
    AuditEvent,
    AuditEventType,
    AuditLevel,
    AuditQuery,
    AuditReport,
    AuditResult,
    AuditStats,
    ExportFormat,
)
from .reporter import (
    AuditReporter,
    export_to_csv,
    export_to_json,
    generate_summary_report,
    get_default_reporter,
)

__all__ = [
    # Models
    "AuditEvent",
    "AuditEventType",
    "AuditLevel",
    "AuditQuery",
    "AuditReport",
    "AuditResult",
    "AuditStats",
    "ExportFormat",
    # Logger
    "AuditLogger",
    "WriteMode",
    "get_default_logger",
    "log_event",
    "log_info",
    "log_warning",
    "log_error",
    "log_critical",
    # Indexer
    "AuditIndexer",
    "get_default_indexer",
    # Reporter
    "AuditReporter",
    "get_default_reporter",
    "generate_summary_report",
    "export_to_csv",
    "export_to_json",
]

# Version
__version__ = "1.0.0"
