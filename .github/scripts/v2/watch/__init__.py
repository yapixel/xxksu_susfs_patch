"""Phase 1 Upstream Auto-Maintenance and Watch subsystem."""

from .model import SourceResult, WatchClassification, WatchReport
from .checker import UpstreamWatcher, compute_composite_hash, fetch_remote_commit
from .dashboard import (
    DASHBOARD_LABEL,
    DASHBOARD_TITLE,
    OverallStatus,
    calculate_overall_status,
    render_dashboard_body,
    sync_dashboard_issue,
)
from .escalation import escalate_issue, format_issue_body, format_issue_title

__all__ = [
    "WatchClassification",
    "SourceResult",
    "WatchReport",
    "UpstreamWatcher",
    "compute_composite_hash",
    "fetch_remote_commit",
    "escalate_issue",
    "format_issue_title",
    "format_issue_body",
    "DASHBOARD_LABEL",
    "DASHBOARD_TITLE",
    "OverallStatus",
    "calculate_overall_status",
    "render_dashboard_body",
    "sync_dashboard_issue",
]
