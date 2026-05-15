#!/usr/bin/env python3
"""
Copy last week's AATS data, SAVE via HTTP, then verify at least one sumup row persisted.

Uses ``filing_week_label_iso`` (upcoming Sunday write-date on Mon–Sat) because mid-week
calendar dates return ``success`` from ``save_report`` but do not persist.

Exit codes:
  0 — already filled, or save + verify OK (substantive >= 1)
  2 — save ran but verify shows no substantive rows
  1 — login/transport/other error
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from aats_http import (  # noqa: E402
    calendar_today_iso,
    copy_last_week_and_save,
    extract_table_list_context,
    fetch_main_html,
    filing_week_label_iso,
    login_ad,
    normalize_login_email,
    open_aats,
    previous_report_date,
)


def run(args: argparse.Namespace) -> int:
    user = os.getenv("AML_USER", "").strip()
    password = os.getenv("AML_PWD", "").strip()
    if not user or not password:
        print("ERROR: Set AML_USER and AML_PWD.", file=sys.stderr)
        return 1

    zone = "Europe/Istanbul"
    target = (args.date or "").strip() or filing_week_label_iso(zone)
    today = calendar_today_iso(zone)
    source = previous_report_date(target)

    session = open_aats(args.base_url)
    login_ad(session, normalize_login_email(user), password)
    html = fetch_main_html(session)
    user_id, department_id, _ = extract_table_list_context(html)

    if args.dry_run:
        print(
            f"DRY RUN: would copy from {source} → save target {target} "
            f"(calendar today {today})"
        )
        return 0

    result = copy_last_week_and_save(
        session,
        user_id,
        department_id,
        target_label=target,
        zone=zone,
    )

    print(json.dumps(result, ensure_ascii=False, indent=2))

    if result.get("error"):
        print(f"ERROR: {result['error']}", file=sys.stderr)

    if result.get("ok"):
        if result.get("already_filled"):
            print(
                f"OK already filled: target={target} substantive={result.get('substantive')} "
                f"(calendar today {today})"
            )
        else:
            print(
                f"OK saved and verified: target={target} copied_rows={result.get('copied_rows')} "
                f"substantive={result.get('substantive')} save={result.get('save_response')!r}"
            )
        return 0

    if result.get("save_response"):
        print(
            f"FAIL: target={target} save={result.get('save_response')!r} "
            f"verify_substantive={result.get('substantive')}",
            file=sys.stderr,
        )
        return 2

    return 1


def build_parser() -> argparse.ArgumentParser:
    default_base = os.getenv("AATS_BASE_URL", "http://aats.amlogic.com").rstrip("/")
    p = argparse.ArgumentParser(description="Copy last week, SAVE, verify AATS weekly report.")
    p.add_argument("--base-url", default=default_base)
    p.add_argument(
        "--date",
        default="",
        help="Target write-date YYYY-MM-DD (default: filing_week_label_iso / upcoming Sunday).",
    )
    p.add_argument("--dry-run", action="store_true")
    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return run(args)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
