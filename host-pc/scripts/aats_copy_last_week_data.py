#!/usr/bin/env python3
"""
HTTP equivalent of clicking **Copy last week's data** (复制上周数据) on AATS.

The SPA does **not** call a dedicated copy URL: it ``POST``s ``/weekly_sumup_fae/table/list``
with ``date = write-date - 7 days``, applies small row transforms, appends one blank row per
section, then leaves the form dirty until the user clicks **保存数据** (``save_report``).

This script:

1. Logs in (same as other tools).
2. Optionally loads **target** week via ``table/list`` (to warn if sumup rows already exist).
3. Loads **previous** week via ``table/list``.
4. Builds the same in-memory row lists as ``copyweek()`` + ``addNewRow`` (see ``aats_http.build_copy_last_week_rows``).

**Persisting** still requires a browser Save or a correct ``save_report`` serialization (raw
``table/list`` JSON is **not** accepted by the server today — see ``saveTeamWork`` in ``main``).

Cron (Friday 13:00, explicit week-end date — adjust ``date`` to match your AATS ``write-date``):

    0 13 * * 5 cd /path/to/aats-weekly-report && \\
      export AML_USER=... AML_PWD=... AATS_BASE_URL=http://10.18.11.124 && \\
      python3 host-pc/scripts/aats_copy_last_week_data.py --date "$(date +%F)" --json-out /tmp/aats-copy.json
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
    build_copy_last_week_rows,
    calendar_today_iso,
    extract_table_list_context,
    fetch_main_html,
    login_ad,
    normalize_login_email,
    open_aats,
    post_table_list,
    previous_report_date,
    save_report,
)


def _count_block(payload: dict[str, Any], key: str) -> int:
    block = payload.get(key)
    if not isinstance(block, dict):
        return 0
    data = block.get("data")
    return len(data) if isinstance(data, list) else 0


def run(args: argparse.Namespace) -> int:
    user = os.getenv("AML_USER", "").strip()
    password = os.getenv("AML_PWD", "").strip()
    if not user or not password:
        print("ERROR: Set AML_USER and AML_PWD.", file=sys.stderr)
        return 1

    session = open_aats(args.base_url)
    login_ad(session, normalize_login_email(user), password)
    html = fetch_main_html(session)
    user_id, department_id, html_write_date = extract_table_list_context(html)
    report_date = (args.date or "").strip() or calendar_today_iso("Europe/Istanbul")

    prev_date = previous_report_date(report_date)
    print(f"Target report date (write-date): {report_date}")
    print(f"Previous week table/list date:  {prev_date}")

    if not args.skip_target_check:
        current = post_table_list(session, user_id, department_id, report_date)
        n_sum = _count_block(current, "sumup")
        n_iss = _count_block(current, "issue")
        n_pln = _count_block(current, "plan")
        print(f"Current week already has: sumup={n_sum} issue={n_iss} plan={n_pln}")
        if n_sum > 0 and not args.force:
            print(
                "WARN: Target week already has sumup rows. "
                "Copy-last-week in the UI would overwrite the form, not merge. "
                "Use --force to continue anyway.",
                file=sys.stderr,
            )
            return 2

    prev_payload = post_table_list(session, user_id, department_id, prev_date)
    ps, pi, pp = _count_block(prev_payload, "sumup"), _count_block(prev_payload, "issue"), _count_block(
        prev_payload, "plan"
    )
    print(f"Previous week returned: sumup={ps} issue={pi} plan={pp}")

    sumups, issues, plans = build_copy_last_week_rows(prev_payload, report_date)
    print(
        f"After copy transform + blank rows: sumup={len(sumups)} issue={len(issues)} plan={len(plans)}"
    )

    if args.json_out:
        out_path = Path(args.json_out)
        out_path.write_text(
            json.dumps({"sumup": sumups, "issue": issues, "plan": plans}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"Wrote merged row preview to {out_path}")

    if args.attempt_save:
        print("INFO: save_report with merged lists (expected to fail until payload matches UI DOM).")
        try:
            body = save_report(
                session,
                sumup_json=json.dumps(sumups, ensure_ascii=False),
                issue_json=json.dumps(issues, ensure_ascii=False),
                plan_json=json.dumps(plans, ensure_ascii=False),
            )
        except Exception as exc:  # noqa: BLE001
            print(f"save_report: {exc}", file=sys.stderr)
            return 1
        print(f"save_report response: {body!r}")
        return 0 if body.strip() == "success" else 1

    print(
        "OK (dry run): same data the SPA loads after **Copy last week's data** "
        "(not persisted until **保存数据** / a correct save_report payload)."
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    default_base = os.getenv("AATS_BASE_URL", "http://aats.amlogic.com").rstrip("/")
    p = argparse.ArgumentParser(
        description="Simulate AATS 'Copy last week's data' via table/list (HTTP, no browser).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--base-url", default=default_base, help="AATS origin (default: env AATS_BASE_URL).")
    p.add_argument(
        "--date",
        default="",
        help="Target week write-date YYYY-MM-DD (required when main HTML has no static write-date value).",
    )
    p.add_argument(
        "--skip-target-check",
        action="store_true",
        help="Do not POST table/list for the target week (skip 'already has rows' guard).",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Continue even when target week already has sumup rows.",
    )
    p.add_argument(
        "--json-out",
        default="",
        help="Write merged sumup/issue/plan row arrays to this JSON file.",
    )
    p.add_argument(
        "--attempt-save",
        action="store_true",
        help="POST save_report after merge (experimental; server often returns HTTP 500).",
    )
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
