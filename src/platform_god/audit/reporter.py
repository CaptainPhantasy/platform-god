"""
Audit report generation for Platform God.

Generates summary reports and exports audit data to various formats.
"""

import csv
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .index import AuditIndexer
from .models import (
    AuditLevel,
    AuditQuery,
    AuditReport,
    AuditStats,
    ExportFormat,
)


class AuditReporter:
    """
    Generate audit reports with filtering and export capabilities.

    Supports summary reports, detailed event lists, and export to
    CSV/JSON formats.
    """

    def __init__(self, indexer: AuditIndexer | None = None):
        """
        Initialize the audit reporter.

        Args:
            indexer: AuditIndexer to query (default: global instance)
        """
        self._indexer = indexer

    @property
    def indexer(self) -> AuditIndexer:
        """Get the indexer instance."""
        if self._indexer is None:
            from .index import get_default_indexer
            self._indexer = get_default_indexer()
        return self._indexer

    def generate_report(
        self,
        query: AuditQuery,
        title: str = "Audit Report",
        description: str | None = None,
    ) -> AuditReport:
        """
        Generate an audit report from a query.

        Args:
            query: AuditQuery defining the report scope
            title: Report title
            description: Optional report description

        Returns:
            AuditReport with matched events and statistics
        """
        import time

        start_time = time.time()

        # Execute query
        events = self.indexer.search(query)

        # Build report
        report_id = f"rpt_{uuid.uuid4().hex[:12]}"
        stats = AuditStats()

        report = AuditReport(
            report_id=report_id,
            generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            query=query,
            stats=stats,
            total_matching=len(events),
            title=title,
            description=description,
        )

        # Add events and update stats
        for event in events:
            report.add_event(event)

        # Record generation time
        report.duration_ms = (time.time() - start_time) * 1000

        return report

    def generate_summary_report(
        self,
        start_time: str | None = None,
        end_time: str | None = None,
        title: str = "Audit Summary Report",
    ) -> AuditReport:
        """
        Generate a summary report for a time range.

        Args:
            start_time: ISO8601 start timestamp (default: 24 hours ago)
            end_time: ISO8601 end timestamp (default: now)
            title: Report title

        Returns:
            AuditReport with summary statistics
        """
        # Default to last 24 hours
        if start_time is None:
            from datetime import timedelta
            start_time = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
        if end_time is None:
            end_time = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        query = AuditQuery(
            start_time=start_time,
            end_time=end_time,
            sort_by="timestamp",
            sort_order="desc",
            limit=10000,  # Higher limit for summary
        )

        return self.generate_report(
            query=query,
            title=title,
            description=f"Summary from {start_time} to {end_time}",
        )

    def generate_security_report(
        self,
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> AuditReport:
        """
        Generate a security-focused report with auth and permission events.

        Args:
            start_time: ISO8601 start timestamp
            end_time: ISO8601 end timestamp

        Returns:
            AuditReport filtered for security events
        """
        from .models import AuditEventType

        # Default to last 24 hours
        if start_time is None:
            from datetime import timedelta
            start_time = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
        if end_time is None:
            end_time = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        query = AuditQuery(
            start_time=start_time,
            end_time=end_time,
            event_types=[
                AuditEventType.AUTH_ATTEMPT,
                AuditEventType.AUTH_SUCCESS,
                AuditEventType.AUTH_FAILURE,
                AuditEventType.PERMISSION_DENIED,
                AuditEventType.UNAUTHORIZED_ACCESS,
                AuditEventType.POLICY_VIOLATION,
            ],
            severities=[
                AuditLevel.WARNING,
                AuditLevel.ERROR,
                AuditLevel.CRITICAL,
            ],
            sort_by="timestamp",
            sort_order="desc",
        )

        return self.generate_report(
            query=query,
            title="Security Audit Report",
            description=f"Security events from {start_time} to {end_time}",
        )

    def generate_agent_report(
        self,
        agent_name: str | None = None,
        run_id: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> AuditReport:
        """
        Generate a report for agent execution activity.

        Args:
            agent_name: Filter by specific agent (actor)
            run_id: Filter by specific run
            start_time: ISO8601 start timestamp
            end_time: ISO8601 end timestamp

        Returns:
            AuditReport for agent activity
        """
        from .models import AuditEventType

        # Default to last 24 hours
        if start_time is None:
            from datetime import timedelta
            start_time = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
        if end_time is None:
            end_time = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        query = AuditQuery(
            start_time=start_time,
            end_time=end_time,
            event_types=[
                AuditEventType.AGENT_START,
                AuditEventType.AGENT_COMPLETE,
                AuditEventType.AGENT_FAIL,
                AuditEventType.AGENT_SKIP,
            ],
            actors=[agent_name] if agent_name else None,
            run_id=run_id,
            sort_by="timestamp",
            sort_order="desc",
        )

        title = f"Agent Report: {agent_name}" if agent_name else "Agent Activity Report"
        if run_id:
            title += f" (Run: {run_id})"

        return self.generate_report(
            query=query,
            title=title,
        )

    def generate_compliance_report(
        self,
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> dict[str, Any]:
        """
        Generate a compliance-focused summary report.

        Returns structured data for compliance audits.

        Args:
            start_time: ISO8601 start timestamp
            end_time: ISO8601 end timestamp

        Returns:
            Dict with compliance metrics and evidence
        """
        # Default to last 30 days for compliance
        if start_time is None:
            from datetime import timedelta
            start_time = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
        if end_time is None:
            end_time = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # Get overall stats
        stats = self.indexer.get_stats()

        # Query for compliance-relevant events
        query = AuditQuery(
            start_time=start_time,
            end_time=end_time,
            sort_by="timestamp",
            sort_order="desc",
            limit=50000,
        )
        events = self.indexer.search(query)

        # Analyze for compliance
        critical_events = [e for e in events if e.severity == AuditLevel.CRITICAL]
        error_events = [e for e in events if e.severity == AuditLevel.ERROR]
        policy_violations = [e for e in events if "violation" in e.action.lower() or "violation" in e.event_type.value]

        # Build compliance report
        return {
            "report_metadata": {
                "report_type": "compliance",
                "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "period_start": start_time,
                "period_end": end_time,
            },
            "summary": {
                "total_events": len(events),
                "critical_events": len(critical_events),
                "error_events": len(error_events),
                "policy_violations": len(policy_violations),
                "compliance_status": "pass" if not critical_events and not policy_violations else "review_required",
            },
            "audit_trail": {
                "total_indexed": stats.get("total_events", 0),
                "time_range": stats.get("time_range"),
                "index_size_bytes": stats.get("index_size_bytes", 0),
            },
            "evidence": {
                "critical_events_sample": [e.model_dump(exclude_none=True) for e in critical_events[:10]],
                "policy_violations_sample": [e.model_dump(exclude_none=True) for e in policy_violations[:10]],
            },
        }

    def export_csv(
        self,
        report: AuditReport,
        output_path: Path | str,
        include_metadata: bool = False,
    ) -> int:
        """
        Export a report to CSV format.

        Args:
            report: AuditReport to export
            output_path: Destination file path
            include_metadata: Include metadata column

        Returns:
            Number of rows written
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Define CSV columns
        columns = [
            "event_id",
            "timestamp",
            "event_type",
            "actor",
            "action",
            "target",
            "result",
            "severity",
            "error_message",
            "correlation_id",
            "run_id",
        ]
        if include_metadata:
            columns.append("metadata")

        written = 0

        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()

            for event in report.events:
                row = {
                    "event_id": event.event_id,
                    "timestamp": event.timestamp,
                    "event_type": event.event_type.value,
                    "actor": event.actor,
                    "action": event.action,
                    "target": event.target or "",
                    "result": event.result.value,
                    "severity": event.severity.value,
                    "error_message": event.error_message or "",
                    "correlation_id": event.correlation_id or "",
                    "run_id": event.run_id or "",
                }
                if include_metadata:
                    row["metadata"] = json.dumps(event.metadata) if event.metadata else ""
                writer.writerow(row)
                written += 1

        return written

    def export_json(
        self,
        report: AuditReport,
        output_path: Path | str,
        pretty: bool = True,
    ) -> None:
        """
        Export a report to JSON format.

        Args:
            report: AuditReport to export
            output_path: Destination file path
            pretty: Pretty-print JSON
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        data = report.to_dict()

        with open(output_path, "w", encoding="utf-8") as f:
            if pretty:
                json.dump(data, f, indent=2)
            else:
                json.dump(data, f)

    def export_events_csv(
        self,
        query: AuditQuery,
        output_path: Path | str,
        include_metadata: bool = False,
    ) -> int:
        """
        Export events matching a query directly to CSV.

        Args:
            query: AuditQuery to filter events
            output_path: Destination file path
            include_metadata: Include metadata column

        Returns:
            Number of rows written
        """
        # Generate report
        report = self.generate_report(query)
        return self.export_csv(report, output_path, include_metadata)

    def export_events_json(
        self,
        query: AuditQuery,
        output_path: Path | str,
        pretty: bool = True,
    ) -> None:
        """
        Export events matching a query directly to JSON.

        Args:
            query: AuditQuery to filter events
            output_path: Destination file path
            pretty: Pretty-print JSON
        """
        # Generate report
        report = self.generate_report(query)
        self.export_json(report, output_path, pretty)

    def export_to_format(
        self,
        report: AuditReport,
        output_path: Path | str,
        format_type: ExportFormat | str = ExportFormat.JSON,
        **kwargs,
    ) -> int | None:
        """
        Export report to specified format.

        Args:
            report: AuditReport to export
            output_path: Destination file path
            format_type: Export format (json or csv)
            **kwargs: Additional options for the format

        Returns:
            Row count for CSV, None for JSON
        """
        if isinstance(format_type, str):
            format_type = ExportFormat(format_type.lower())

        if format_type == ExportFormat.CSV:
            return self.export_csv(report, output_path, kwargs.get("include_metadata", False))
        elif format_type == ExportFormat.JSON:
            self.export_json(report, output_path, kwargs.get("pretty", True))
        else:
            raise ValueError(f"Unsupported format: {format_type}")

    def get_top_actors(self, limit: int = 10) -> list[dict[str, Any]]:
        """
        Get top actors by event count.

        Args:
            limit: Maximum number of actors to return

        Returns:
            List of dicts with actor, count, and breakdown
        """
        stats = self.indexer.get_stats()
        actors = stats.get("top_actors", {})

        # Get more detailed breakdown for top actors
        result = []
        for actor, count in sorted(actors.items(), key=lambda x: x[1], reverse=True)[:limit]:
            # Query events for this actor
            query = AuditQuery(actors=[actor], limit=1000)
            events = self.indexer.search(query)

            # Break down by result type
            by_result: dict[str, int] = {}
            for event in events:
                result_val = event.result.value
                by_result[result_val] = by_result.get(result_val, 0) + 1

            result.append({
                "actor": actor,
                "total_events": count,
                "by_result": by_result,
            })

        return result

    def get_severity_summary(self, start_time: str | None = None, end_time: str | None = None) -> dict[str, Any]:
        """
        Get event counts by severity level for a time range.

        Args:
            start_time: ISO8601 start timestamp
            end_time: ISO8601 end timestamp

        Returns:
            Dict with severity breakdown
        """
        query = AuditQuery(
            start_time=start_time,
            end_time=end_time,
            limit=100000,
        )

        events = self.indexer.search(query)

        by_severity: dict[str, int] = {}
        for event in events:
            sev = event.severity.value
            by_severity[sev] = by_severity.get(sev, 0) + 1

        return {
            "period": {
                "start": start_time,
                "end": end_time,
            },
            "by_severity": by_severity,
            "total_events": len(events),
        }


# Global default reporter
_default_reporter: AuditReporter | None = None


def get_default_reporter() -> AuditReporter:
    """Get or create the default global audit reporter."""
    global _default_reporter

    if _default_reporter is None:
        _default_reporter = AuditReporter()
    return _default_reporter


def generate_summary_report(
    start_time: str | None = None,
    end_time: str | None = None,
) -> AuditReport:
    """Generate a summary report using the default reporter."""
    return get_default_reporter().generate_summary_report(start_time, end_time)


def export_to_csv(
    query: AuditQuery,
    output_path: Path | str,
) -> int:
    """Export events to CSV using the default reporter."""
    return get_default_reporter().export_events_csv(query, output_path)


def export_to_json(
    query: AuditQuery,
    output_path: Path | str,
    pretty: bool = True,
) -> None:
    """Export events to JSON using the default reporter."""
    return get_default_reporter().export_events_json(query, output_path, pretty)
