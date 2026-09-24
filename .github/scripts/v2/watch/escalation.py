"""Issue escalation handler for AGY-required upstream drift."""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from typing import Optional

from .model import SourceResult

logger = logging.getLogger(__name__)


def format_issue_title(result: SourceResult) -> str:
    """Format structured title for AGY escalation issue."""
    return f"[AGY-REQUIRED] Upstream Drift: {result.source_id} ({result.classification.value})"


def format_issue_body(result: SourceResult) -> str:
    """Format structured markdown body with immutable identities and reproduction steps."""
    affected_files_str = "\n".join(f"- `{f}`" for f in result.affected_files) if result.affected_files else "- None detected"
    affected_semantics_str = "\n".join(f"- `{s}`" for s in result.affected_semantics) if result.affected_semantics else "- None recorded"

    return f"""## Upstream Drift Escalation Report

### 1. Source Identity
- **Source ID:** `{result.source_id}`
- **Source Type:** `{result.source_type}`
- **Classification:** `{result.classification.value}`
- **Old Identity:** `{result.old_identity}`
- **New Identity:** `{result.new_identity}`
- **Old Content Hash:** `{result.old_content_hash}`
- **New Content Hash:** `{result.new_content_hash}`

### 2. Affected Semantic Units & Files
#### Affected Files:
{affected_files_str}

#### Affected Semantics / Anchors:
{affected_semantics_str}

### 3. Failure & Drift Diagnostics
```
{result.details}
```

### 4. Deterministic Reproduction Command
```bash
{result.reproduction_command}
```

---
*Generated automatically by Phase 1 Upstream Auto-Maintenance (`upstream-watch.yml`).*
"""


def escalate_issue(
    result: SourceResult,
    repo: str = "yapixel/xxksu_susfs_patch",
) -> Optional[str]:
    """Create or comment on a structured GitHub Issue labeled 'agy-required'.

    Returns the issue URL if created or updated, or None if skipped/unavailable.
    """
    if not result.requires_escalation():
        return None

    if not shutil.which("gh"):
        logger.warning("gh CLI not available; skipping issue escalation.")
        return None

    title = format_issue_title(result)
    body = format_issue_body(result)

    # 1. Search for existing open issue to avoid duplicates
    try:
        list_cmd = [
            "gh", "issue", "list",
            "--repo", repo,
            "--state", "open",
            "--label", "agy-required",
            "--json", "number,title,url",
        ]
        list_proc = subprocess.run(list_cmd, capture_output=True, text=True, check=True)
        open_issues = json.loads(list_proc.stdout)
        for issue in open_issues:
            if result.source_id in issue.get("title", ""):
                issue_num = issue["number"]
                issue_url = issue["url"]
                logger.info("Found existing open issue #%s for %s; updating with comment.", issue_num, result.source_id)
                comment_cmd = [
                    "gh", "issue", "comment", str(issue_num),
                    "--repo", repo,
                    "--body", f"### Upstream Watch Re-check Update\n\n{body}",
                ]
                subprocess.run(comment_cmd, capture_output=True, text=True, check=True)
                return issue_url
    except Exception as exc:
        logger.warning("Error checking existing issues via gh: %s", exc)

    # 2. Create new issue if none exists
    try:
        create_cmd = [
            "gh", "issue", "create",
            "--repo", repo,
            "--title", title,
            "--label", "agy-required",
            "--body", body,
        ]
        create_proc = subprocess.run(create_cmd, capture_output=True, text=True, check=True)
        issue_url = create_proc.stdout.strip()
        logger.info("Created AGY escalation issue: %s", issue_url)
        return issue_url
    except subprocess.CalledProcessError as exc:
        logger.error("Failed to create GitHub issue via gh: %s (stderr: %s)", exc, exc.stderr)
        return None


__all__ = [
    "format_issue_title",
    "format_issue_body",
    "escalate_issue",
]
