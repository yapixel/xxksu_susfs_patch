"""CLI driver for upstream watch, candidate generation, and issue escalation."""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
import sys

from .checker import UpstreamWatcher
from .escalation import escalate_issue
from .model import WatchClassification, WatchReport

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def generate_markdown_summary(report: WatchReport) -> str:
    lines = [
        "## 🛰️ Upstream Watch & Auto-Maintenance Report (Phase 1)",
        f"- **Timestamp:** `{report.timestamp}`",
        "",
        "| Source | Type | Classification | Old Identity | New Identity | Candidate Patch |",
        "| :--- | :--- | :--- | :--- | :--- | :--- |",
    ]
    for r in report.results:
        cand_str = f"✅ `{r.candidate_patch_name}`" if r.candidate_patch else "—"
        badge = "🟢" if r.classification in (WatchClassification.NO_CHANGE, WatchClassification.IRRELEVANT_CHANGE) else (
            "🔵" if r.classification == WatchClassification.SAFE_REGEN_CANDIDATE else (
                "🟡" if r.classification == WatchClassification.REFERENCE_DRIFT else "🔴"
            )
        )
        lines.append(
            f"| `{r.source_id}` | `{r.source_type}` | {badge} `{r.classification.value}` | `{r.old_identity[:12]}` | `{r.new_identity[:12]}` | {cand_str} |"
        )

    lines.append("")
    lines.append("### Details & Diagnostics")
    for r in report.results:
        lines.append(f"<details><summary><b>{r.source_id}</b> — <code>{r.classification.value}</code></summary>")
        lines.append("")
        lines.append(f"- **Old Content Hash:** `{r.old_content_hash}`")
        lines.append(f"- **New Content Hash:** `{r.new_content_hash}`")
        if r.affected_files:
            lines.append(f"- **Affected Files:** {', '.join(f'`{f}`' for f in r.affected_files)}")
        if r.affected_semantics:
            lines.append(f"- **Affected Semantics / Anchors:** {', '.join(f'`{s}`' for s in r.affected_semantics)}")
        lines.append("")
        lines.append("```")
        lines.append(r.details)
        lines.append("```")
        lines.append("")
        lines.append("</details>")
        lines.append("")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Upstream Watch & Auto-Maintenance (Phase 1)")
    parser.add_argument("--state-file", type=Path, default=Path(".github/upstream-state.json"), help="Path to upstream state JSON")
    parser.add_argument("--repo-root", type=Path, default=Path("."), help="Path to repository root")
    parser.add_argument("--candidate-dir", type=Path, default=Path("candidate_patches"), help="Output directory for candidate patches")
    parser.add_argument("--escalate", action="store_true", help="Escalate failures to GitHub Issues labeled agy-required")
    parser.add_argument("--dry-run", action="store_true", help="Skip remote fetches (test mode)")
    parser.add_argument("--source", type=str, default=None, help="Filter check to a specific source ID")
    parser.add_argument("--json", action="store_true", help="Print report in JSON format")

    args = parser.parse_args(argv)

    watcher = UpstreamWatcher(repo_root=args.repo_root, state_path=args.state_file)
    logger.info("Running upstream watch checks (dry_run=%s, source=%s)...", args.dry_run, args.source)
    report = watcher.run_all(fetch_remote=not args.dry_run, source_filter=args.source)

    # Save candidate patches
    if report.has_candidates:
        args.candidate_dir.mkdir(parents=True, exist_ok=True)
        for r in report.results:
            if r.candidate_patch and r.candidate_patch_name:
                cand_path = args.candidate_dir / r.candidate_patch_name
                cand_path.write_text(r.candidate_patch, encoding="utf-8")
                logger.info("Saved candidate patch to %s", cand_path)

    # Handle escalations
    escalations = []
    if args.escalate:
        repo_slug = os.environ.get("GITHUB_REPOSITORY", "yapixel/xxksu_susfs_patch")
        for r in report.results:
            if r.requires_escalation():
                issue_url = escalate_issue(r, repo=repo_slug)
                if issue_url:
                    escalations.append({"source_id": r.source_id, "url": issue_url})

    if escalations:
        report = WatchReport(results=report.results, timestamp=report.timestamp, escalations=tuple(escalations))

    # Output
    summary_md = generate_markdown_summary(report)
    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        with open(step_summary, "a", encoding="utf-8") as f:
            f.write(summary_md + "\n")

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(summary_md)

    # Verify patches manifest consistency
    from ..manifests.patch_manifest import verify_patch_manifest
    manifest_ok, manifest_errs = verify_patch_manifest()
    if not manifest_ok:
        logger.error("patches/manifest.json verification failed: %s", manifest_errs)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
