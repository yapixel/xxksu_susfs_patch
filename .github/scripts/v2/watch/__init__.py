"""Phase 1 Upstream Auto-Maintenance and Watch subsystem."""

from .checker import UpstreamWatcher, compute_composite_hash, fetch_remote_commit
from .escalation import escalate_issue, format_issue_body, format_issue_title
from .model import SourceResult, WatchClassification, WatchReport

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
]
