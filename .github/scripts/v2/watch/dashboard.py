"""Persistent GitHub Issue dashboard renderer and updater for Upstream Watch.

Maintains exactly one persistent issue titled '📡 Upstream Watch Status' labeled 'upstream-status'.
Renders bounded current-state overview (overall status, sources, production patches from manifest,
open escalations, and up to 10 recent state transition events).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import json
import logging
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any, Mapping, Optional, Sequence, Tuple

from .model import SourceResult, WatchClassification, WatchReport

logger = logging.getLogger(__name__)

DASHBOARD_TITLE = "📡 Upstream Watch Status"
DASHBOARD_LABEL = "upstream-status"
MAX_BODY_BYTES = 30 * 1024  # 30 KiB internal soft limit
MAX_DISPLAYED_ESCALATIONS = 5
MAX_RECENT_EVENTS = 10

SOURCE_DISPLAY_NAMES = {
    "backslashxx_kernelsu": "xxKSU",
    "susfs_sultan": "SuSFS Sultan 6.1",
    "susfs_gki": "SuSFS GKI 6.12",
    "midori_kernelsu_xx_patch": "Midori xx.patch",
    "midori_gki_patch_50": "Midori GKI 50 Patch",
}

DEFAULT_INITIAL_EVENTS: Tuple[Mapping[str, str], ...] = (
    {
        "timestamp": "2026-09-24",
        "source_id": "watch",
        "text": "Activated reference-patch normalization (commit rebase with identical normalized patch is NO_CHANGE)",
    },
    {
        "timestamp": "2026-09-24",
        "source_id": "backslashxx_kernelsu",
        "text": "Promoted authoritative bb0be929 pin and regenerated Patch 11 (resolved Issue #4)",
    },
    {
        "timestamp": "2026-09-23",
        "source_id": "susfs_sultan",
        "text": "Promoted authoritative c254cf2d pin, expanded bundle with fs/super.c, and regenerated Patch 51 (resolved Issue #3)",
    },
    {
        "timestamp": "2026-09-23",
        "source_id": "susfs_gki",
        "text": "Promoted authoritative 2528bdb0 pin and regenerated Patch 51 (resolved Issue #2)",
    },
    {
        "timestamp": "2026-09-23",
        "source_id": "backslashxx_kernelsu",
        "text": "Promoted authoritative 41c73d28 pin and regenerated Patch 11 (resolved Issue #1)",
    },
)


class OverallStatus(str, Enum):
    """Overall health classification for the upstream watch dashboard."""
    HEALTHY = "🟢 HEALTHY"
    UPDATE_AVAILABLE = "🔵 UPDATE AVAILABLE"
    REVIEW_REQUIRED = "🟠 REVIEW REQUIRED"
    ACTION_REQUIRED = "🔴 ACTION REQUIRED"


def get_repo_root(repo_root: Optional[Path] = None) -> Path:
    if repo_root is not None:
        return repo_root.resolve()
    # v2/watch/dashboard.py -> 4 levels up to repo root
    return Path(__file__).resolve().parents[4]


def calculate_overall_status(
    report: WatchReport,
    open_escalations: Sequence[Mapping[str, Any]] = (),
) -> OverallStatus:
    """Calculate overall status following authoritative precedence rules.

    - ACTION_REQUIRED (🔴):
        Authoritative ANCHOR_DRIFT, SEMANTIC_DRIFT, SOURCE_IDENTITY_ERROR,
        or any open authoritative escalation.
    - UPDATE_AVAILABLE (🔵):
        At least one authoritative source is a verified SAFE_REGEN_CANDIDATE.
    - REVIEW_REQUIRED (🟠):
        Reference-only content drift; authoritative production is unaffected.
    - HEALTHY (🟢):
        All authoritative sources NO_CHANGE and no open authoritative escalations.

    Authoritative state strictly takes precedence over reference-only state.
    A reference change never independently marks production as broken.
    """
    authoritative_sources = {"backslashxx_kernelsu", "susfs_sultan", "susfs_gki"}

    # 1. Authoritative failures or open authoritative escalations
    authoritative_failures = [
        r for r in report.results
        if r.source_type == "authoritative" and (
            r.classification in (
                WatchClassification.ANCHOR_DRIFT,
                WatchClassification.SEMANTIC_DRIFT,
                WatchClassification.SOURCE_IDENTITY_ERROR,
            )
            or r.requires_escalation()
        )
    ]
    open_auth_escalations = [
        esc for esc in open_escalations
        if esc.get("source_id") in authoritative_sources
    ]
    if authoritative_failures or open_auth_escalations:
        return OverallStatus.ACTION_REQUIRED

    # 2. Authoritative SAFE_REGEN_CANDIDATE
    authoritative_candidates = [
        r for r in report.results
        if r.source_type == "authoritative" and r.classification == WatchClassification.SAFE_REGEN_CANDIDATE
    ]
    if authoritative_candidates:
        return OverallStatus.UPDATE_AVAILABLE

    # 3. Reference-only drift (non-blocking)
    reference_drifts = [
        r for r in report.results
        if r.source_type == "reference" and r.classification == WatchClassification.REFERENCE_DRIFT
    ]
    if reference_drifts:
        return OverallStatus.REVIEW_REQUIRED

    # 4. Default healthy
    return OverallStatus.HEALTHY


def load_manifest_patches(repo_root: Optional[Path] = None) -> list[dict[str, Any]]:
    """Load public production patch outputs from patches/manifest.json."""
    root = get_repo_root(repo_root)
    manifest_path = root / "patches" / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")

    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    patches = data.get("patches", [])
    if not patches:
        raise ValueError("No patches found in patches/manifest.json")
    return list(patches)


def parse_dashboard_events(body: str) -> list[dict[str, str]]:
    """Extract stored recent events from previous issue body."""
    if not body:
        return []

    # 1. Try embedded JSON comment
    m = re.search(r"<!--\s*dashboard-events:\s*(\[.*?\])\s*-->", body, re.DOTALL)
    if m:
        try:
            parsed = json.loads(m.group(1))
            if isinstance(parsed, list):
                return [
                    {
                        "timestamp": str(e.get("timestamp", "")),
                        "source_id": str(e.get("source_id", "")),
                        "text": str(e.get("text", "")),
                    }
                    for e in parsed
                    if isinstance(e, dict)
                ]
        except Exception:
            pass

    # 2. Fallback to markdown lines under ## Recent Events
    events = []
    in_events = False
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("## Recent Events"):
            in_events = True
            continue
        elif in_events and line.startswith("## "):
            break
        elif in_events and line.startswith("- "):
            m_line = re.match(r"-\s+\*\*(?P<ts>[^*]+)\*\*:\s+`(?P<src>[^`]+)`\s+[—\-]\s+(?P<txt>.*)", line)
            if m_line:
                events.append({
                    "timestamp": m_line.group("ts").strip(),
                    "source_id": m_line.group("src").strip(),
                    "text": m_line.group("txt").strip(),
                })
    return events


def extract_transition_events(report: WatchReport, date_str: str) -> list[dict[str, str]]:
    """Extract meaningful state transitions from the current report.

    Routine NO_CHANGE or IRRELEVANT_CHANGE runs produce zero events.
    """
    events: list[dict[str, str]] = []
    for r in report.results:
        if r.classification in (
            WatchClassification.ANCHOR_DRIFT,
            WatchClassification.SEMANTIC_DRIFT,
            WatchClassification.SOURCE_IDENTITY_ERROR,
        ):
            events.append({
                "timestamp": date_str,
                "source_id": r.source_id,
                "text": f"Drift detected: {r.classification.value} (old: `{r.old_identity[:8]}`, new: `{r.new_identity[:8]}`)",
            })
        elif r.classification == WatchClassification.SAFE_REGEN_CANDIDATE:
            cand_name = r.candidate_patch_name or "candidate"
            events.append({
                "timestamp": date_str,
                "source_id": r.source_id,
                "text": f"Candidate patch generated (`{cand_name}`)",
            })
        elif r.classification == WatchClassification.REFERENCE_DRIFT:
            events.append({
                "timestamp": date_str,
                "source_id": r.source_id,
                "text": f"Reference patch content drift detected (`{r.new_content_hash[:12]}`)",
            })
    return events


def combine_recent_events(
    existing_events: Sequence[Mapping[str, str]],
    new_events: Sequence[Mapping[str, str]],
    max_events: int = MAX_RECENT_EVENTS,
) -> list[dict[str, str]]:
    """Combine existing and new transition events, capped to max_events."""
    if not existing_events and not new_events:
        return [dict(e) for e in DEFAULT_INITIAL_EVENTS[:max_events]]

    combined: list[dict[str, str]] = []
    seen = set()

    for e in new_events:
        key = (e.get("source_id", ""), e.get("text", ""))
        if key not in seen:
            seen.add(key)
            combined.append(dict(e))

    for e in existing_events:
        key = (e.get("source_id", ""), e.get("text", ""))
        if key not in seen:
            seen.add(key)
            combined.append(dict(e))

    return combined[:max_events]


def fetch_open_escalations(repo: str) -> list[dict[str, Any]]:
    """Query currently open agy-required issues via gh CLI."""
    if not shutil.which("gh"):
        return []
    try:
        cmd = [
            "gh", "issue", "list",
            "--repo", repo,
            "--state", "open",
            "--label", "agy-required",
            "--json", "number,title,url",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
        raw_issues = json.loads(proc.stdout)
        results = []
        for issue in raw_issues:
            title = issue.get("title", "")
            # Title pattern: [AGY-REQUIRED] Upstream Drift: <source_id> (<classification>)
            m = re.search(r"Upstream Drift:\s*(\w+)\s*\(([^)]+)\)", title)
            source_id = m.group(1) if m else "unknown"
            classification = m.group(2) if m else "AGY_REQUIRED"
            results.append({
                "number": issue.get("number"),
                "title": title,
                "url": issue.get("url", ""),
                "source_id": source_id,
                "classification": classification,
            })
        return results
    except Exception as exc:
        logger.warning("Failed to fetch open escalations via gh: %s", exc)
        return []


def find_dashboard_issues(repo: str) -> list[dict[str, Any]]:
    """Find all open issues with the upstream-status label."""
    if not shutil.which("gh"):
        return []
    try:
        cmd = [
            "gh", "issue", "list",
            "--repo", repo,
            "--state", "open",
            "--label", DASHBOARD_LABEL,
            "--json", "number,title,url,body",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return json.loads(proc.stdout)
    except Exception as exc:
        logger.warning("Failed to query dashboard issues via gh: %s", exc)
        return []


def ensure_label_exists(repo: str, label: str) -> None:
    """Ensure the dashboard label exists in the repository."""
    if not shutil.which("gh"):
        return
    try:
        subprocess.run(
            [
                "gh", "label", "create", label,
                "--repo", repo,
                "--description", "Persistent upstream watch dashboard",
                "--color", "0E8A16",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception as exc:
        logger.debug("Label creation note: %s", exc)


def create_dashboard_issue(repo: str, body: str) -> str:
    """Create a new dashboard issue and return its URL."""
    cmd = [
        "gh", "issue", "create",
        "--repo", repo,
        "--title", DASHBOARD_TITLE,
        "--label", DASHBOARD_LABEL,
        "--body", body,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return proc.stdout.strip()


def update_dashboard_issue(repo: str, issue_number: int, body: str) -> str:
    """Update existing dashboard issue body in place."""
    cmd = [
        "gh", "issue", "edit", str(issue_number),
        "--repo", repo,
        "--title", DASHBOARD_TITLE,
        "--body", body,
    ]
    subprocess.run(cmd, capture_output=True, text=True, check=True)
    return f"https://github.com/{repo}/issues/{issue_number}"


def get_git_revision(repo_root: Path) -> tuple[str, str]:
    """Retrieve current commit hash and branch name."""
    rev = os.environ.get("GITHUB_SHA")
    branch = os.environ.get("GITHUB_REF_NAME")
    if rev and branch:
        return rev[:7], branch
    try:
        rev_proc = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--short=7", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        rev = rev_proc.stdout.strip()
    except Exception:
        rev = "unknown"
    try:
        branch_proc = subprocess.run(
            ["git", "-C", str(repo_root), "branch", "--show-current"],
            capture_output=True,
            text=True,
            check=True,
        )
        branch = branch_proc.stdout.strip() or "main"
    except Exception:
        branch = "main"
    return rev, branch


def render_dashboard_body(
    report: WatchReport,
    repo_root: Optional[Path] = None,
    open_escalations: Sequence[Mapping[str, Any]] = (),
    recent_events: Sequence[Mapping[str, str]] = (),
    server_url: str = "https://github.com",
    repo: str = "yapixel/xxksu_susfs_patch",
    run_id: Optional[str] = None,
    revision: Optional[str] = None,
    branch: Optional[str] = None,
) -> str:
    """Render the complete Markdown dashboard body."""
    root = get_repo_root(repo_root)
    overall_status = calculate_overall_status(report, open_escalations)

    if revision is None or branch is None:
        rev_val, branch_val = get_git_revision(root)
        revision = revision or rev_val
        branch = branch or branch_val

    # Actions run link
    if run_id:
        actions_str = f"[Workflow Run #{run_id}]({server_url}/{repo}/actions/runs/{run_id})"
    else:
        actions_str = "*Manual / Local Execution*"

    # 1. Header & Overall Status
    lines = [
        f"# {DASHBOARD_TITLE}",
        "",
        f"**Overall Status:** {overall_status.value}",
        "",
        f"- **Last Evaluated:** `{report.timestamp}`",
        f"- **Watcher Revision:** `{revision}` (`{branch}`)",
        f"- **Actions Run:** {actions_str}",
        "",
        "## Upstream Sources",
        "",
        "| Source | Type | Status | Current Identity | Discovered Upstream | Escalation |",
        "| :--- | :--- | :--- | :--- | :--- | :--- |",
    ]

    # Map results by source_id
    results_map = {r.source_id: r for r in report.results}

    # Order sources deterministically: authoritative first, then reference
    tracked_source_order = [
        ("backslashxx_kernelsu", "Authoritative"),
        ("susfs_sultan", "Authoritative"),
        ("susfs_gki", "Authoritative"),
        ("midori_kernelsu_xx_patch", "Reference Only"),
        ("midori_gki_patch_50", "Reference Only"),
    ]

    for source_id, s_type in tracked_source_order:
        disp_name = SOURCE_DISPLAY_NAMES.get(source_id, source_id)
        if source_id in results_map:
            r = results_map[source_id]
            badge_map = {
                WatchClassification.NO_CHANGE: "🟢 `NO_CHANGE`",
                WatchClassification.IRRELEVANT_CHANGE: "🟢 `IRRELEVANT_CHANGE`",
                WatchClassification.SAFE_REGEN_CANDIDATE: "🔵 `SAFE_REGEN_CANDIDATE`",
                WatchClassification.REFERENCE_DRIFT: "🟠 `REFERENCE_DRIFT`",
                WatchClassification.ANCHOR_DRIFT: "🔴 `ANCHOR_DRIFT`",
                WatchClassification.SEMANTIC_DRIFT: "🔴 `SEMANTIC_DRIFT`",
                WatchClassification.SOURCE_IDENTITY_ERROR: "🔴 `SOURCE_IDENTITY_ERROR`",
            }
            status_badge = badge_map.get(r.classification, f"🔴 `{r.classification.value}`")

            # Current identity
            curr_id = r.old_identity[:12] if r.old_identity else r.old_content_hash[:12]

            # Discovered upstream
            if r.new_identity and r.new_identity != r.old_identity:
                disc_up = f"`{r.new_identity[:12]}`"
            else:
                disc_up = "—"
        else:
            # Fallback if filtered
            status_badge = "🟢 `NO_CHANGE`"
            curr_id = "—"
            disc_up = "—"

        # Linked escalation
        matching_esc = [esc for esc in open_escalations if esc.get("source_id") == source_id]
        if matching_esc:
            esc_item = matching_esc[0]
            esc_str = f"[#{esc_item['number']}]({esc_item['url']})" if esc_item.get("url") else f"#{esc_item['number']}"
        else:
            esc_str = "—"

        lines.append(
            f"| `{disp_name}` | {s_type} | {status_badge} | `{curr_id}` | {disc_up} | {esc_str} |"
        )

    # 2. Production Patches (from manifest.json)
    lines.append("")
    lines.append("## Production Patches")
    lines.append("")
    lines.append("| Patch ID | Relative Path | SHA-256 | Compatibility / Apply Target |")
    lines.append("| :--- | :--- | :--- | :--- |")

    patches = load_manifest_patches(root)
    for p in patches:
        pid = p.get("id", "—")
        rel_path = p.get("relative_path", "—")
        sha_abbr = p.get("sha256", "")[:12]
        compat = p.get("compatibility_target") or p.get("patch_apply_target") or p.get("apply_target") or "—"
        lines.append(f"| `{pid}` | `{rel_path}` | `{sha_abbr}` | {compat} |")

    # 3. Open Escalations
    lines.append("")
    lines.append("## Open Escalations")
    lines.append("")
    if not open_escalations:
        lines.append("*No open escalations.*")
    else:
        for esc in open_escalations[:MAX_DISPLAYED_ESCALATIONS]:
            num = esc.get("number")
            url = esc.get("url", "")
            src = esc.get("source_id", "unknown")
            cls_name = esc.get("classification", "AGY_REQUIRED")
            link_str = f"[#{num}]({url})" if url else f"#{num}"
            lines.append(f"- {link_str} — `{src}`: `{cls_name}`")
        if len(open_escalations) > MAX_DISPLAYED_ESCALATIONS:
            rem = len(open_escalations) - MAX_DISPLAYED_ESCALATIONS
            lines.append(f"- *+ {rem} additional open escalations*")

    # 4. Recent Events
    lines.append("")
    lines.append("## Recent Events")
    lines.append("")
    if not recent_events:
        lines.append("*No recent state transitions recorded.*")
    else:
        for ev in recent_events[:MAX_RECENT_EVENTS]:
            ts = ev.get("timestamp", "")
            src = ev.get("source_id", "")
            txt = ev.get("text", "")
            lines.append(f"- **{ts}**: `{src}` — {txt}")

    # 5. Quick Links
    manifest_link = f"{server_url}/{repo}/blob/{branch}/patches/manifest.json"
    runs_link = f"{server_url}/{repo}/actions/workflows/upstream-watch.yml"
    issues_link = f"{server_url}/{repo}/issues?q=is%3Aissue+is%3Aopen+label%3Aagy-required"

    lines.append("")
    lines.append("## Quick Links")
    lines.append(f"- [patches/manifest.json]({manifest_link})")
    lines.append(f"- [Upstream Watch Workflow Runs]({runs_link})")
    lines.append(f"- [Open `agy-required` Issues]({issues_link})")
    lines.append("")

    # 6. Bounded state serialization comment
    events_json = json.dumps(list(recent_events[:MAX_RECENT_EVENTS]))
    lines.append(f"<!-- dashboard-events: {events_json} -->")

    return "\n".join(lines) + "\n"


def trim_body_if_needed(
    body: str,
    recent_events: list[dict[str, str]],
    open_escalations: Sequence[Mapping[str, Any]],
    report: WatchReport,
    repo_root: Optional[Path] = None,
    server_url: str = "https://github.com",
    repo: str = "yapixel/xxksu_susfs_patch",
    run_id: Optional[str] = None,
    revision: Optional[str] = None,
    branch: Optional[str] = None,
) -> str:
    """Enforce the internal soft maximum of 30 KiB UTF-8.

    Trimming order:
    1. Shorten / remove oldest Recent Events
    2. Shorten optional descriptions in events
    3. Collapse excess escalation summaries
    Never trims overall status, source states, production patch identities, or escalation links.
    """
    body_bytes = len(body.encode("utf-8"))
    if body_bytes <= MAX_BODY_BYTES:
        return body

    logger.warning("Rendered body exceeds 30 KiB (%d bytes); trimming...", body_bytes)

    # Trim 1: drop oldest events down to 5 or fewer
    events_copy = list(recent_events)
    while len(events_copy) > 3 and body_bytes > MAX_BODY_BYTES:
        events_copy = events_copy[: len(events_copy) - 2]
        body = render_dashboard_body(
            report=report,
            repo_root=repo_root,
            open_escalations=open_escalations,
            recent_events=events_copy,
            server_url=server_url,
            repo=repo,
            run_id=run_id,
            revision=revision,
            branch=branch,
        )
        body_bytes = len(body.encode("utf-8"))
        if body_bytes <= MAX_BODY_BYTES:
            return body

    # Trim 2: shorten optional descriptions in events
    shortened_events = [
        {
            "timestamp": e.get("timestamp", ""),
            "source_id": e.get("source_id", ""),
            "text": (e.get("text", "")[:40] + "...") if len(e.get("text", "")) > 40 else e.get("text", ""),
        }
        for e in events_copy
    ]
    body = render_dashboard_body(
        report=report,
        repo_root=repo_root,
        open_escalations=open_escalations,
        recent_events=shortened_events,
        server_url=server_url,
        repo=repo,
        run_id=run_id,
        revision=revision,
        branch=branch,
    )
    body_bytes = len(body.encode("utf-8"))
    if body_bytes <= MAX_BODY_BYTES:
        return body

    # Trim 3: shorten escalation summaries
    shortened_escalations = [
        {
            "number": esc.get("number"),
            "url": esc.get("url", ""),
            "source_id": esc.get("source_id", ""),
            "classification": esc.get("classification", ""),
            "title": "",
        }
        for esc in open_escalations
    ]
    body = render_dashboard_body(
        report=report,
        repo_root=repo_root,
        open_escalations=shortened_escalations,
        recent_events=shortened_events,
        server_url=server_url,
        repo=repo,
        run_id=run_id,
        revision=revision,
        branch=branch,
    )
    body_bytes = len(body.encode("utf-8"))
    if body_bytes <= MAX_BODY_BYTES:
        return body

    raise ValueError(f"Dashboard body exceeds soft maximum of 30 KiB even after trimming ({body_bytes} bytes)")


def sync_dashboard_issue(
    report: WatchReport,
    repo: str = "yapixel/xxksu_susfs_patch",
    repo_root: Optional[Path] = None,
    dry_run: bool = False,
    run_id: Optional[str] = None,
    revision: Optional[str] = None,
    branch: Optional[str] = None,
) -> tuple[Optional[str], bool]:
    """Synchronize the permanent dashboard issue in GitHub.

    Lifecycle:
    1. Find open issue with label 'upstream-status'.
    2. If none exists: create exactly one.
    3. If exactly one exists: update in place (no comments).
    4. If more than one exists: fail closed and report duplicate condition.

    Returns:
        tuple[issue_url, created_bool]
    """
    root = get_repo_root(repo_root)
    server_url = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    run_id = run_id or os.environ.get("GITHUB_RUN_ID")

    # 1. Search for existing dashboard issue(s)
    matching_issues = find_dashboard_issues(repo)
    if len(matching_issues) > 1:
        issue_nums = [i.get("number") for i in matching_issues]
        raise RuntimeError(
            f"Duplicate dashboard condition: found {len(matching_issues)} open issues with label "
            f"'{DASHBOARD_LABEL}': {issue_nums}. Fail-closed: human intervention required to deduplicate."
        )

    # 2. Extract existing events from previous issue body
    existing_events = []
    if len(matching_issues) == 1:
        existing_body = matching_issues[0].get("body", "")
        existing_events = parse_dashboard_events(existing_body)

    # 3. Query open escalations
    open_escalations = fetch_open_escalations(repo)

    # 4. Extract new transition events from this run
    date_str = report.timestamp[:10] if report.timestamp else datetime.now(timezone.utc).strftime("%Y-%m-%d")
    new_events = extract_transition_events(report, date_str)

    # 5. Combine events bounded to MAX_RECENT_EVENTS
    combined_events = combine_recent_events(existing_events, new_events, max_events=MAX_RECENT_EVENTS)

    # 6. Render body and enforce bounded limits (<= 30 KiB)
    raw_body = render_dashboard_body(
        report=report,
        repo_root=root,
        open_escalations=open_escalations,
        recent_events=combined_events,
        server_url=server_url,
        repo=repo,
        run_id=run_id,
        revision=revision,
        branch=branch,
    )
    final_body = trim_body_if_needed(
        body=raw_body,
        recent_events=combined_events,
        open_escalations=open_escalations,
        report=report,
        repo_root=root,
        server_url=server_url,
        repo=repo,
        run_id=run_id,
        revision=revision,
        branch=branch,
    )

    if dry_run:
        logger.info("[Dry Run] Rendered dashboard (%d bytes UTF-8); skipping issue sync.", len(final_body.encode("utf-8")))
        return ("dry-run", False)

    # 7. Create or update issue
    if len(matching_issues) == 0:
        ensure_label_exists(repo, DASHBOARD_LABEL)
        issue_url = create_dashboard_issue(repo, final_body)
        logger.info("Created permanent dashboard issue: %s", issue_url)
        return (issue_url, True)
    else:
        issue_num = matching_issues[0]["number"]
        issue_url = update_dashboard_issue(repo, issue_num, final_body)
        logger.info("Updated permanent dashboard issue #%s in place: %s", issue_num, issue_url)
        return (issue_url, False)


__all__ = [
    "DASHBOARD_TITLE",
    "DASHBOARD_LABEL",
    "MAX_BODY_BYTES",
    "MAX_DISPLAYED_ESCALATIONS",
    "MAX_RECENT_EVENTS",
    "OverallStatus",
    "calculate_overall_status",
    "load_manifest_patches",
    "parse_dashboard_events",
    "extract_transition_events",
    "combine_recent_events",
    "fetch_open_escalations",
    "find_dashboard_issues",
    "render_dashboard_body",
    "trim_body_if_needed",
    "sync_dashboard_issue",
]
