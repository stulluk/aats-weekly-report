#!/usr/bin/env python3
"""
Experimental: append text to the ``notes`` field (Others / comment style text)
for one sumup row, then POST /weekly_sumup_fae/save_report.

Loads the current week from ``table/list``, updates one row, and saves all rows
back together so nothing else is dropped.

**Status:** As of 2026-05-03 the AATS server responds with HTTP 500 (Spring cannot
bind ``workType`` from our reconstructed JSON). Use DevTools → Network on a real
Save to capture the exact ``sumup`` JSON shape, or use browser automation until
the payload matches the UI.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from aats_http import (  # noqa: E402
    extract_table_list_context,
    fetch_main_html,
    login_ad,
    normalize_login_email,
    open_aats,
    post_table_list,
    save_report,
)


def _iso_week_number(label: str) -> str:
    """Week number string aligned with browser ``#weeknum`` (ISO week, Monday-based)."""
    day = dt.date.fromisoformat(label)
    return str(day.isocalendar()[1])


def _prepare_row_for_save(row: dict[str, Any]) -> dict[str, Any]:
    """
    Build a minimal payload row similar to the Vue form POST (trial heuristic).

    The full ``table/list`` row includes display-only keys that break Spring
    binding (``workType`` becomes null). We keep only fields that map cleanly to
    ``WeeklySumup`` plus ``project.id`` and ``weekNum``.
    """
    label = str(row.get("label") or "")
    week_num = _iso_week_number(label) if label else ""
    pid = row.get("projectId")
    wt = row.get("workType")
    try:
        wt_str = str(int(wt)) if wt not in (None, "") else ""
    except (TypeError, ValueError):
        wt_str = str(wt) if wt is not None else ""
    return {
        "id": row.get("id"),
        "label": label,
        "weekNum": week_num,
        "sequence": row.get("sequence"),
        "statement": row.get("statement"),
        "workTime": row.get("workTime"),
        "workType": wt_str,
        "project.id": pid,
        "notes": row.get("notes") if row.get("notes") is not None else "",
        "jiraId": row.get("jiraId") or "",
        "reason": row.get("reason") or "",
        "departmentId": row.get("departmentId"),
        "projectId": pid,
        "stillOnWork": bool(row.get("stillOnWork")),
        "isOnTime": bool(row.get("isOnTime")),
        "finishCount": row.get("finishCount", 0.0),
        "projectFullPath": row.get("projectFullPath") or "",
        "workTypeHaveDefaultProject": bool(row.get("workTypeHaveDefaultProject")),
    }


def run(args: argparse.Namespace) -> int:
    """Fetch rows, append notes text on one sequence, save, print server response."""
    user = os.getenv("AML_USER", "").strip()
    password = os.getenv("AML_PWD", "").strip()
    if not user or not password:
        print("ERROR: Set AML_USER and AML_PWD.", file=sys.stderr)
        return 1

    session = open_aats(args.base_url)
    login_ad(session, normalize_login_email(user), password)
    html = fetch_main_html(session)
    user_id, department_id, default_date = extract_table_list_context(html)
    report_date = args.date or default_date
    if not report_date:
        print("ERROR: Pass --date YYYY-MM-DD.", file=sys.stderr)
        return 1

    payload = post_table_list(
        session,
        user_id=user_id,
        department_id=department_id,
        report_date=report_date,
    )
    block = payload.get("sumup")
    if not isinstance(block, dict):
        print("ERROR: Unexpected sumup block.", file=sys.stderr)
        return 1
    rows_in = block.get("data")
    if not isinstance(rows_in, list):
        print("ERROR: sumup.data is not a list.", file=sys.stderr)
        return 1

    updated: list[dict[str, Any]] = []
    found = False
    for row in rows_in:
        if not isinstance(row, dict):
            continue
        r = _prepare_row_for_save(row)
        if int(r.get("sequence", -1)) == args.sequence:
            found = True
            prev = str(r.get("notes") or "")
            add = args.append_text
            if add and add not in prev:
                r["notes"] = (prev + add).strip() if prev else add.strip()
            elif add and add in prev:
                print(f"INFO: Append text already present on row {args.sequence}; no change.")
        updated.append(r)

    if not found:
        print(f"ERROR: No row with sequence={args.sequence}.", file=sys.stderr)
        return 1

    sumup_json = json.dumps(updated, ensure_ascii=False)
    issue_json = json.dumps(
        payload.get("issue", {}).get("data", []) if isinstance(payload.get("issue"), dict) else [],
        ensure_ascii=False,
    )
    plan_json = json.dumps(
        payload.get("plan", {}).get("data", []) if isinstance(payload.get("plan"), dict) else [],
        ensure_ascii=False,
    )

    if args.dry_run:
        print("DRY RUN — would POST sumup preview (first 800 chars):")
        print(sumup_json[:800])
        return 0

    body = save_report(
        session,
        sumup_json=sumup_json,
        issue_json=issue_json,
        plan_json=plan_json,
    )
    print(f"save_report response: {body!r}")
    if body.strip() != "success":
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    """CLI for experimental notes append."""
    default_base = os.getenv("AATS_BASE_URL", "http://aats.amlogic.com").rstrip("/")
    p = argparse.ArgumentParser(description="Append to sumup ``notes`` for one row (experimental).")
    p.add_argument("--base-url", default=default_base)
    p.add_argument("--date", required=True, help="Report date passed to table/list (YYYY-MM-DD).")
    p.add_argument("--sequence", type=int, default=4, help="Row sequence to edit (default: 4).")
    p.add_argument(
        "--append-text",
        default=" still in progress",
        help="Suffix to append to notes when not already present (default: ' still in progress').",
    )
    p.add_argument("--dry-run", action="store_true", help="Print payload only; do not save.")
    return p


def main() -> int:
    """Entry point."""
    parser = build_parser()
    args = parser.parse_args()
    try:
        return run(args)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
