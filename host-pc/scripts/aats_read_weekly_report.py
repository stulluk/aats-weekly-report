#!/usr/bin/env python3
"""
Read the current user's weekly AATS report rows for a given report date.

This uses the same HTTP endpoints as the browser (login + table/list POST).
Run on a host that can reach AATS (corporate VPN when required).
"""

from __future__ import annotations

import argparse
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
)


def _preview(text: str, limit: int = 120) -> str:
    """Return a single-line preview for terminal output."""
    one = " ".join(text.split())
    if len(one) <= limit:
        return one
    return one[: limit - 3] + "..."


def _print_sumups(rows: list[dict[str, Any]]) -> None:
    """Print weekly work rows in a stable, human-readable shape."""
    if not rows:
        print("  (no sumup rows returned)")
        return
    for row in rows:
        seq = row.get("sequence", "?")
        wt = row.get("workTime", "")
        wt_type = row.get("workType", "")
        pid = row.get("projectId", "")
        stmt = _preview(str(row.get("statement", "") or ""))
        done = row.get("completed", row.get("isCompleted", ""))
        overdue = row.get("overdue", "")
        print(f"  - row {seq}: type={wt_type!r} projectId={pid!r} hours={wt!r} completed={done!r} overdue={overdue!r}")
        if stmt:
            print(f"      task: {stmt}")


def _print_generic_block(label: str, rows: Any) -> None:
    """Print issues or plans arrays when present."""
    if rows in (None, "", []):
        print(f"{label}: (none)")
        return
    if not isinstance(rows, list):
        print(f"{label}: {json.dumps(rows, ensure_ascii=False)[:400]}")
        return
    print(f"{label}: {len(rows)} row(s)")
    for row in rows:
        if isinstance(row, dict):
            seq = row.get("sequence", "?")
            stmt = _preview(str(row.get("statement", "") or ""))
            print(f"  - row {seq}: {stmt}")
        else:
            print(f"  - {row}")


def run(args: argparse.Namespace) -> int:
    """CLI entry: login, discover ids, fetch table/list, print summary."""
    user = os.getenv("AML_USER", "").strip()
    password = os.getenv("AML_PWD", "").strip()
    if not user or not password:
        print("ERROR: Set AML_USER and AML_PWD in the environment.", file=sys.stderr)
        return 1

    session = open_aats(args.base_url)
    email = normalize_login_email(user)
    login_ad(session, email, password)
    html = fetch_main_html(session)
    user_id, department_id, default_date = extract_table_list_context(html)
    report_date = args.date or default_date
    if not report_date:
        print("ERROR: Could not determine report date; pass --date YYYY-MM-DD.", file=sys.stderr)
        return 1

    payload = post_table_list(
        session,
        user_id=user_id,
        department_id=department_id,
        report_date=report_date,
        work_type=args.work_type,
        fetch_all=args.fetch_all,
    )

    print(f"AATS report date: {report_date}")
    print(f"Resolved user id={user_id} department id={department_id}")
    if args.dump_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    sumup_block = payload.get("sumup") if isinstance(payload, dict) else None
    issue_block = payload.get("issue") if isinstance(payload, dict) else None
    plan_block = payload.get("plan") if isinstance(payload, dict) else None

    sum_rows: list[dict[str, Any]] = []
    if isinstance(sumup_block, dict):
        data = sumup_block.get("data")
        if isinstance(data, list):
            sum_rows = [r for r in data if isinstance(r, dict)]

    print(f"Weekly work rows (sumup): {len(sum_rows)}")
    _print_sumups(sum_rows)

    issue_rows = None
    if isinstance(issue_block, dict):
        issue_rows = issue_block.get("data")
    _print_generic_block("Issues", issue_rows)

    plan_rows = None
    if isinstance(plan_block, dict):
        plan_rows = plan_block.get("data")
    _print_generic_block("Next week plans", plan_rows)

    return 0


def build_parser() -> argparse.ArgumentParser:
    """Configure CLI flags."""
    default_base = os.getenv("AATS_BASE_URL", "http://aats.amlogic.com").rstrip("/")
    parser = argparse.ArgumentParser(description="Read AATS weekly report rows (HTTP, no browser).")
    parser.add_argument(
        "--base-url",
        default=default_base,
        help="AATS origin including host and port (default: env AATS_BASE_URL or internal host).",
    )
    parser.add_argument(
        "--date",
        default="",
        help="Report date YYYY-MM-DD (defaults to write-date from /weekly_sumup_fae/main).",
    )
    parser.add_argument("--work-type", type=int, default=-1, help="workType filter (default: -1).")
    parser.add_argument("--fetch-all", default="100", help="fetchAll parameter (default: 100).")
    parser.add_argument(
        "--dump-json",
        action="store_true",
        help="Print full JSON response instead of a short summary.",
    )
    return parser


def main() -> int:
    """Program entry point."""
    parser = build_parser()
    args = parser.parse_args()
    try:
        return run(args)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
