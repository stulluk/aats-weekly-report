#!/usr/bin/env python3
"""
Check whether AATS already has **meaningful** weekly sumup content for a report date.

Uses the same flow as the reader: login, ``GET /weekly_sumup_fae/main``, then
``POST /weekly_sumup_fae/table/list`` for ``--date``.

**Filled** means: at least one ``sumup`` row with a non-empty ``statement`` **or**
``workTime >= 0.5`` (same spirit as the web form’s “has a task line / hours”).

Exit codes:

- ``0`` — filled for that date.
- ``1`` — credentials missing, login/HTTP/parse error.
- ``2`` — reachable but not filled (no sumup rows, or none with content).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from aats_http import (  # noqa: E402
    calendar_today_iso,
    count_substantive_sumups,
    extract_table_list_context,
    fetch_main_html,
    filing_week_label_iso,
    login_ad,
    normalize_login_email,
    open_aats,
    post_table_list,
)


def run(args: argparse.Namespace) -> int:
    user = os.getenv("AML_USER", "").strip()
    password = os.getenv("AML_PWD", "").strip()
    if not user or not password:
        print("ERROR: Set AML_USER and AML_PWD.", file=sys.stderr)
        return 1

    session = open_aats(args.base_url)
    login_ad(session, normalize_login_email(user), password)
    html = fetch_main_html(session)
    user_id, department_id, _html_write_date = extract_table_list_context(html)

    zone = "Europe/Istanbul"
    report_date = (args.date or "").strip() or filing_week_label_iso(zone)
    today = calendar_today_iso(zone)

    payload = post_table_list(session, user_id, department_id, report_date)
    block = payload.get("sumup") if isinstance(payload, dict) else None
    data = block.get("data") if isinstance(block, dict) else []
    rows_n = len(data) if isinstance(data, list) else 0
    substantive_n = count_substantive_sumups(payload)
    filled = substantive_n > 0

    line = (
        f"AATS write-date {report_date} (calendar today {today}): "
        f"sumup_rows={rows_n} substantive={substantive_n} "
        f"filled={'yes' if filled else 'no'} (user={user_id})"
    )
    print(line)

    if filled:
        return 0
    return 2


def build_parser() -> argparse.ArgumentParser:
    default_base = os.getenv("AATS_BASE_URL", "http://aats.amlogic.com").rstrip("/")
    p = argparse.ArgumentParser(description="Check AATS weekly sumup is filled for a date (HTTP).")
    p.add_argument("--base-url", default=default_base)
    p.add_argument(
        "--date",
        default="",
        help="Report write-date YYYY-MM-DD (default: upcoming Sunday / filing_week_label_iso).",
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
