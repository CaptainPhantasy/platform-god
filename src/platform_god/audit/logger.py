"""
Audit log writer for Platform God.

Provides thread-safe, async-capable audit logging to JSONL files.
"""

import asyncio
import fcntl
import os
import threading
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from pydantic import ValidationError

from .models import AuditEvent, AuditLevel, AuditEventType


class WriteMode(str, Enum):
    """Write mode for audit logging."""

    SYNC = "sync"
    ASYNC = "async"
    BATCH = "batch"


@dataclass
class WriteResult:
    """Result of a log write operation."""

    success: bool
    event_id: str
    log_file: str
    error: str | None = None
    bytes_written: int = 0


class AuditLogger:
    """
    Thread-safe audit log writer.

    Writes structured audit events to var/audit/ with date-based filenames.
    Supports synchronous, asynchronous, and batch write modes.
    """

    DEFAULT_AUDIT_DIR = Path("var/audit")
    LOG_PREFIX = "audit_"
    LOG_SUFFIX = ".jsonl"

    def __init__(
        self,
        audit_dir: Path | None = None,
        write_mode: WriteMode = WriteMode.SYNC,
        batch_size: int = 100,
        batch_flush_interval_sec: float = 5.0,
    ):
        """
        Initialize the audit logger.

        Args:
            audit_dir: Directory for audit log files (default: var/audit/)
            write_mode: How to write logs (sync, async, batch)
            batch_size: Number of events to batch before flushing
            batch_flush_interval_sec: Seconds between batch flushes
        """
        self._audit_dir = Path(audit_dir) if audit_dir else self.DEFAULT_AUDIT_DIR
        self._audit_dir.mkdir(parents=True, exist_ok=True)
        self._write_mode = write_mode
        self._batch_size = batch_size
        self._batch_flush_interval_sec = batch_flush_interval_sec

        # Thread safety
        self._lock = threading.RLock()
        self._file_locks: dict[str, threading.Lock] = {}
        self._file_lock = threading.Lock()  # For _file_locks dict access

        # Async batch queue
        self._batch_queue: deque[AuditEvent] = deque()
        self._batch_executor: ThreadPoolExecutor | None = None
        self._batch_flush_task: asyncio.Task | None = None
        self._flush_event: threading.Event | None = None
        self._running = False

        # Start background processing for async/batch modes
        if write_mode in (WriteMode.ASYNC, WriteMode.BATCH):
            self._start_background_writer()

    def _get_log_file(self, date: datetime | None = None) -> Path:
        """Get the log file path for a specific date."""
        if date is None:
            date = datetime.now(timezone.utc)
        filename = f"{self.LOG_PREFIX}{date.strftime('%Y%m%d')}{self.LOG_SUFFIX}"
        return self._audit_dir / filename

    def _get_file_lock(self, file_path: str) -> threading.Lock:
        """Get or create a file-specific lock for concurrent writes."""
        with self._file_lock:
            if file_path not in self._file_locks:
                self._file_locks[file_path] = threading.Lock()
            return self._file_locks[file_path]

    def _write_sync(self, event: AuditEvent) -> WriteResult:
        """Synchronously write an event to its log file."""
        log_file = self._get_log_file()
        log_file_str = str(log_file)

        # Get file-specific lock
        file_lock = self._get_file_lock(log_file_str)

        try:
            # Convert to JSONL
            log_line = event.to_log_line() + "\n"
            bytes_to_write = len(log_line.encode("utf-8"))

            # Write with file locking for cross-process safety
            with file_lock:
                # Use atomic append mode
                with open(log_file, "a", encoding="utf-8") as f:
                    # Acquire exclusive lock (non-blocking)
                    try:
                        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                    except (AttributeError, OSError):
                        # fcntl not available on Windows or lock failed
                        pass

                    try:
                        f.write(log_line)
                        f.flush()
                        # Ensure write to disk
                        os.fsync(f.fileno())
                    finally:
                        try:
                            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                        except (AttributeError, OSError):
                            pass

            return WriteResult(
                success=True,
                event_id=event.event_id,
                log_file=log_file_str,
                bytes_written=bytes_to_write,
            )

        except (IOError, OSError) as e:
            return WriteResult(
                success=False,
                event_id=event.event_id,
                log_file=log_file_str,
                error=str(e),
            )

    def _write_batch_sync(self, events: list[AuditEvent]) -> list[WriteResult]:
        """Write multiple events efficiently in batch."""
        if not events:
            return []

        # Group by date/file
        by_file: dict[Path, list[AuditEvent]] = {}
        for event in events:
            log_file = self._get_log_file()
            if log_file not in by_file:
                by_file[log_file] = []
            by_file[log_file].append(event)

        results = []
        for log_file, file_events in by_file.items():
            log_file_str = str(log_file)
            file_lock = self._get_file_lock(log_file_str)

            try:
                # Prepare all lines
                lines = [e.to_log_line() for e in file_events]
                content = "\n".join(lines) + "\n"
                bytes_to_write = len(content.encode("utf-8"))

                with file_lock:
                    with open(log_file, "a", encoding="utf-8") as f:
                        try:
                            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                        except (AttributeError, OSError):
                            pass

                        try:
                            f.write(content)
                            f.flush()
                            os.fsync(f.fileno())
                        finally:
                            try:
                                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                            except (AttributeError, OSError):
                                pass

                # Create success result for each event
                for event in file_events:
                    results.append(
                        WriteResult(
                            success=True,
                            event_id=event.event_id,
                            log_file=log_file_str,
                            bytes_written=bytes_to_write // len(file_events),
                        )
                    )

            except (IOError, OSError) as e:
                # Create failure result for each event
                for event in file_events:
                    results.append(
                        WriteResult(
                            success=False,
                            event_id=event.event_id,
                            log_file=log_file_str,
                            error=str(e),
                        )
                    )

        return results

    def _start_background_writer(self) -> None:
        """Start background thread/task for async/batch writing."""
        with self._lock:
            if self._running:
                return

            self._running = True
            self._batch_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="audit_writer")
            self._flush_event = threading.Event()

            if self._write_mode == WriteMode.BATCH:
                # Start periodic flush thread
                flush_thread = threading.Thread(
                    target=self._periodic_flush,
                    daemon=True,
                    name="audit_batch_flush",
                )
                flush_thread.start()

    def _stop_background_writer(self) -> None:
        """Stop background writer and flush pending events."""
        with self._lock:
            if not self._running:
                return

            self._running = False

            # Signal flush event
            if self._flush_event:
                self._flush_event.set()

        # Flush any remaining events
        self._flush()

        # Shutdown executor
        if self._batch_executor:
            self._batch_executor.shutdown(wait=True)
            self._batch_executor = None

    def _periodic_flush(self) -> None:
        """Background thread that periodically flushes the batch queue."""
        while self._running:
            if self._flush_event:
                # Wait for flush interval or stop signal
                self._flush_event.wait(timeout=self._batch_flush_interval_sec)
                if not self._running:
                    break
                self._flush()
                self._flush_event.clear()

    def _flush(self) -> None:
        """Flush all pending events from the batch queue."""
        with self._lock:
            if not self._batch_queue:
                return

            events = list(self._batch_queue)
            self._batch_queue.clear()

        if events and self._batch_executor:
            self._batch_executor.submit(self._write_batch_sync, events)

    def log(self, event: AuditEvent) -> WriteResult:
        """
        Log an audit event.

        Args:
            event: The audit event to log

        Returns:
            WriteResult with success status and details
        """
        # Validate event
        if not isinstance(event, AuditEvent):
            try:
                event = AuditEvent(**event)
            except (ValidationError, TypeError) as e:
                return WriteResult(
                    success=False,
                    event_id="unknown",
                    log_file="",
                    error=f"Invalid event: {e}",
                )

        # Route based on write mode
        if self._write_mode == WriteMode.SYNC:
            return self._write_sync(event)
        elif self._write_mode == WriteMode.BATCH:
            with self._lock:
                self._batch_queue.append(event)
                # Flush if batch size reached
                if len(self._batch_queue) >= self._batch_size:
                    events = list(self._batch_queue)
                    self._batch_queue.clear()
                    if self._batch_executor:
                        self._batch_executor.submit(self._write_batch_sync, events)
                        # Return immediate success for batch mode
                        return WriteResult(
                            success=True,
                            event_id=event.event_id,
                            log_file=str(self._get_log_file()),
                        )
            return WriteResult(
                success=True,
                event_id=event.event_id,
                log_file=str(self._get_log_file()),
            )
        else:  # ASYNC mode
            if self._batch_executor:
                self._batch_executor.submit(self._write_sync, event)
            return WriteResult(
                success=True,
                event_id=event.event_id,
                log_file=str(self._get_log_file()),
            )

    async def log_async(self, event: AuditEvent) -> WriteResult:
        """
        Asynchronously log an audit event.

        Args:
            event: The audit event to log

        Returns:
            WriteResult with success status and details
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.log, event)

    def log_batch(self, events: list[AuditEvent]) -> list[WriteResult]:
        """
        Log multiple audit events efficiently.

        Args:
            events: List of audit events to log

        Returns:
            List of WriteResult objects
        """
        if not events:
            return []

        if self._write_mode == WriteMode.SYNC:
            return self._write_batch_sync(events)
        else:
            # Add to batch queue
            results = []
            for event in events:
                result = self.log(event)
                results.append(result)
            return results

    async def log_batch_async(self, events: list[AuditEvent]) -> list[WriteResult]:
        """
        Asynchronously log multiple audit events.

        Args:
            events: List of audit events to log

        Returns:
            List of WriteResult objects
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.log_batch, events)

    def flush(self) -> None:
        """Manually flush any pending batched events."""
        self._flush()

    def close(self) -> None:
        """Close the audit logger and flush pending writes."""
        self._stop_background_writer()

    def __enter__(self) -> "AuditLogger":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.close()

    # Convenience methods for quick logging

    def info(
        self,
        action: str,
        actor: str = "system",
        target: str | None = None,
        event_type: AuditEventType | str = AuditEventType.CUSTOM,
        **metadata,
    ) -> WriteResult:
        """Log an info-level event."""
        if isinstance(event_type, str):
            event_type = AuditEventType(event_type)

        event = AuditEvent(
            action=action,
            actor=actor,
            target=target,
            event_type=event_type,
            severity=AuditLevel.INFO,
            metadata=metadata,
        )
        return self.log(event)

    def warning(
        self,
        action: str,
        actor: str = "system",
        target: str | None = None,
        event_type: AuditEventType | str = AuditEventType.CUSTOM,
        **metadata,
    ) -> WriteResult:
        """Log a warning-level event."""
        if isinstance(event_type, str):
            event_type = AuditEventType(event_type)

        event = AuditEvent(
            action=action,
            actor=actor,
            target=target,
            event_type=event_type,
            severity=AuditLevel.WARNING,
            metadata=metadata,
        )
        return self.log(event)

    def error(
        self,
        action: str,
        error_message: str | None = None,
        actor: str = "system",
        target: str | None = None,
        event_type: AuditEventType | str = AuditEventType.SYSTEM_ERROR,
        **metadata,
    ) -> WriteResult:
        """Log an error-level event."""
        if isinstance(event_type, str):
            event_type = AuditEventType(event_type)

        event = AuditEvent(
            action=action,
            actor=actor,
            target=target,
            event_type=event_type,
            severity=AuditLevel.ERROR,
            error_message=error_message,
            metadata=metadata,
        )
        return self.log(event)

    def critical(
        self,
        action: str,
        error_message: str | None = None,
        actor: str = "system",
        target: str | None = None,
        event_type: AuditEventType | str = AuditEventType.SYSTEM_ERROR,
        **metadata,
    ) -> WriteResult:
        """Log a critical-level event."""
        if isinstance(event_type, str):
            event_type = AuditEventType(event_type)

        event = AuditEvent(
            action=action,
            actor=actor,
            target=target,
            event_type=event_type,
            severity=AuditLevel.CRITICAL,
            error_message=error_message,
            metadata=metadata,
        )
        return self.log(event)


# Global default logger instance
_default_logger: AuditLogger | None = None
_default_lock = threading.Lock()


def get_default_logger() -> AuditLogger:
    """Get or create the default global audit logger."""
    global _default_logger

    with _default_lock:
        if _default_logger is None:
            _default_logger = AuditLogger()
        return _default_logger


def log_event(event: AuditEvent) -> WriteResult:
    """Log an event using the default logger."""
    return get_default_logger().log(event)


def log_info(action: str, **kwargs) -> WriteResult:
    """Log an info event using the default logger."""
    return get_default_logger().info(action, **kwargs)


def log_warning(action: str, **kwargs) -> WriteResult:
    """Log a warning event using the default logger."""
    return get_default_logger().warning(action, **kwargs)


def log_error(action: str, **kwargs) -> WriteResult:
    """Log an error event using the default logger."""
    return get_default_logger().error(action, **kwargs)


def log_critical(action: str, **kwargs) -> WriteResult:
    """Log a critical event using the default logger."""
    return get_default_logger().critical(action, **kwargs)
