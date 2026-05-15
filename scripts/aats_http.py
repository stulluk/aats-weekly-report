"""
Minimal HTTP helpers for AATS (cookie jar, login, POST form).

English-only module for reuse by host-pc and dumpling tools.
"""

from __future__ import annotations

import copy
import datetime as dt
import http.cookiejar
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


def calendar_today_iso(zone: str = "Europe/Istanbul") -> str:
    """Today's date in ``YYYY-MM-DD`` for the given IANA timezone (UI write-date style)."""
    try:
        from zoneinfo import ZoneInfo

        return dt.datetime.now(ZoneInfo(zone)).date().isoformat()
    except (ImportError, ModuleNotFoundError, OSError):
        pass
    # Python < 3.9 or missing tzdata: Turkey uses UTC+3 year-round (no DST since 2018).
    if zone == "Europe/Istanbul":
        ist = dt.timezone(dt.timedelta(hours=3))
        return dt.datetime.now(ist).date().isoformat()
    return dt.datetime.now(dt.timezone.utc).date().isoformat()


def date_in_zone(zone: str = "Europe/Istanbul") -> dt.date:
    """Today's ``datetime.date`` in ``zone``."""
    return dt.date.fromisoformat(calendar_today_iso(zone))


def filing_week_label_iso(zone: str = "Europe/Istanbul") -> str:
    """
    AATS ``write-date`` for the week being filed (week-ending Sunday).

    Mon–Sat: upcoming Sunday (e.g. Friday 2026-05-15 → label 2026-05-17).
    Sunday: today. Calendar mid-week dates alone are off-week and do not persist.
    """
    today = date_in_zone(zone)
    days_ahead = (6 - today.weekday()) % 7
    target = today if days_ahead == 0 else today + dt.timedelta(days=days_ahead)
    return target.isoformat()


def weekly_label_sunday_iso(zone: str = "Europe/Istanbul") -> str:
    """
    Return the weekly report label date as the most recent Sunday in ``zone``.

    On Friday checks, this maps to the previous Sunday (what users commonly
    use as ``write-date`` in AATS weekly reports).
    """
    today = dt.date.fromisoformat(calendar_today_iso(zone))
    # Python weekday: Monday=0 ... Sunday=6
    days_since_sunday = (today.weekday() + 1) % 7
    return (today - dt.timedelta(days=days_since_sunday)).isoformat()


@dataclass
class AatsSession:
    """Logged-in session state for weekly_sumup_fae."""

    base_url: str
    opener: urllib.request.OpenerDirector


def normalize_login_email(raw_user: str) -> str:
    """Append @amlogic.com when the UI email tab expects a corporate suffix."""
    user = raw_user.strip()
    if not user:
        raise ValueError("AML_USER is empty.")
    if "@" in user:
        return user
    return f"{user}@amlogic.com"


def build_opener() -> urllib.request.OpenerDirector:
    """Create an opener that stores cookies like a browser session."""
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def login_ad(session: AatsSession, email: str, password: str) -> None:
    """
    POST /weekly_sumup_fae/user/login/ad (same as the web Email tab).

    Raises:
        urllib.error.HTTPError / URLError on transport failure.
        RuntimeError when the response does not look like a successful login.
    """
    path = "/weekly_sumup_fae/user/login/ad"
    url = urllib.parse.urljoin(session.base_url, path)
    body = urllib.parse.urlencode({"email": email, "password": password}).encode("utf-8")
    req = urllib.request.Request(url=url, data=body, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with session.opener.open(req, timeout=60) as resp:
        final_url = resp.geturl()
        html = resp.read().decode("utf-8", errors="replace")
    if "Signin Amlogic Weekly Sumup" in html or "Signin" in html and "Weekly Sumup" in html:
        raise RuntimeError("Login appears to have failed (still on sign-in page).")
    if "/weekly_sumup_fae/user/login" in final_url and "main" not in final_url:
        raise RuntimeError(f"Unexpected redirect after login: {final_url}")


def fetch_main_html(session: AatsSession) -> str:
    """GET the weekly report shell page after login."""
    url = urllib.parse.urljoin(session.base_url, "/weekly_sumup_fae/main")
    req = urllib.request.Request(url=url, method="GET")
    with session.opener.open(req, timeout=60) as resp:
        return resp.read().decode("utf-8", errors="replace")


def extract_table_list_context(html: str) -> tuple[str, str, str | None]:
    """
    Parse user id, department id, and default write-date from embedded JS.

    Returns:
        (user_id, department_id, write_date or None)
    """
    # Primary: first ajax block that posts to /weekly_sumup_fae/table/list with id + departmentid.
    marker = "/weekly_sumup_fae/table/list"
    pos = html.find(marker)
    if pos == -1:
        raise RuntimeError("Could not find /weekly_sumup_fae/table/list in main HTML.")
    window = html[pos : pos + 2500]
    id_m = re.search(r'"id"\s*:\s*"(\d+)"', window)
    dep_m = re.search(r"departmentid['\"]\s*:\s*[\"'](\d+)[\"']", window)
    if not id_m or not dep_m:
        raise RuntimeError("Could not parse user id / departmentid near table/list call.")
    write_date = extract_write_date_from_main_html(html)
    return id_m.group(1), dep_m.group(1), write_date


def extract_write_date_from_main_html(html: str) -> str | None:
    """
    Parse the report ``write-date`` from ``/weekly_sumup_fae/main`` HTML.

    Newer pages use ``<input type="date" id="write-date">`` with **no** static
    ``value=`` attribute (the browser sets it at runtime). In that case this
    returns ``None`` and callers should pass an explicit ``--date``.
    """
    m = re.search(r'<input[^>]*\bid="write-date"[^>]*>', html, re.I)
    if not m:
        return None
    tag = m.group(0)
    vm = re.search(r'value="(20\d{2}-\d{2}-\d{2})"', tag, re.I)
    return vm.group(1) if vm else None


def previous_report_date(report_date: str) -> str:
    """Return ``report_date`` minus seven days (``YYYY-MM-DD``), same as ``copyweek()``."""
    day = dt.date.fromisoformat(report_date)
    return (day - dt.timedelta(days=7)).isoformat()


def iso_week_number_str(report_date: str) -> str:
    """ISO week number string (matches common ``#weeknum`` usage in this app)."""
    day = dt.date.fromisoformat(report_date)
    return str(day.isocalendar()[1])


def apply_copy_last_week_sumup_transform(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Mirror ``copyweek()`` in ``main`` HTML: clear persisted ids, set treeselect flags.

    Operates on deep copies so callers can keep the original ``table/list`` payload.
    """
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        r = copy.deepcopy(row)
        r["id"] = ""
        wth = bool(r.get("workTypeHaveDefaultProject"))
        r["treeDisabled"] = wth
        if wth:
            r["projectId"] = 0
        out.append(r)
    return out


def empty_sumup_row_after_copy(sequence: int) -> dict[str, Any]:
    """Blank sumup row appended after ``copyweek()`` (Vue ``addNewRow('sumup')``)."""
    return {
        "id": "",
        "sequence": sequence,
        "jiraId": "无",
        "statement": "",
        "project": "",
        "projectId": None,
        "workTime": "",
        "finishCount": "",
        "isOnTime": True,
        "reason": "",
        "notes": "",
        "workType": 1,
        "treeDisabled": False,
    }


def empty_issue_row_after_copy(sequence: int) -> dict[str, Any]:
    """Blank issue row after ``copyweek()``."""
    return {
        "id": "",
        "sequence": sequence,
        "statement": "",
        "suggest": "",
        "isSolve": "",
        "needAssist": "",
    }


def empty_plan_row_after_copy(sequence: int) -> dict[str, Any]:
    """Blank plan row after ``copyweek()``."""
    return {
        "id": "",
        "sequence": sequence,
        "statement": "",
    }


def build_copy_last_week_rows(
    previous_week_payload: dict[str, Any],
    target_label: str,
    *,
    week_num: str | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Build ``sumups`` / ``issues`` / ``plans`` lists as the SPA does after ``copyweek()``.

    This is the **in-memory** state before the user clicks **保存数据**; persisting
    still requires a correct ``save_report`` body (see README / ``saveTeamWork`` in
    ``main`` HTML — the UI serializes from DOM inputs, not raw ``table/list`` JSON).
    """
    wn = week_num if week_num is not None else iso_week_number_str(target_label)

    raw_sum = previous_week_payload.get("sumup", {})
    raw_iss = previous_week_payload.get("issue", {})
    raw_pln = previous_week_payload.get("plan", {})
    sumups = apply_copy_last_week_sumup_transform(
        raw_sum.get("data", []) if isinstance(raw_sum, dict) else []
    )
    issues = copy.deepcopy(raw_iss.get("data", [])) if isinstance(raw_iss, dict) else []
    plans = copy.deepcopy(raw_pln.get("data", [])) if isinstance(raw_pln, dict) else []
    if not isinstance(issues, list):
        issues = []
    if not isinstance(plans, list):
        plans = []

    sumup_id = len(sumups)
    issue_id = len(issues)
    plan_id = len(plans)

    sumups.append(empty_sumup_row_after_copy(sumup_id + 1))
    issues.append(empty_issue_row_after_copy(issue_id + 1))
    plans.append(empty_plan_row_after_copy(plan_id + 1))

    for i, row in enumerate(sumups, start=1):
        if isinstance(row, dict):
            row["sequence"] = i
            row["label"] = target_label
            row["weekNum"] = wn
    for i, row in enumerate(issues, start=1):
        if isinstance(row, dict):
            row["sequence"] = i
            row["label"] = target_label
            row["weekNum"] = wn
    for i, row in enumerate(plans, start=1):
        if isinstance(row, dict):
            row["sequence"] = i
            row["label"] = target_label
            row["weekNum"] = wn

    return sumups, issues, plans


def post_table_list(
    session: AatsSession,
    user_id: str,
    department_id: str,
    report_date: str,
    work_type: int = -1,
    fetch_all: str = "100",
) -> dict[str, Any]:
    """
    POST /weekly_sumup_fae/table/list — returns parsed JSON object.

    The server responds with a JSON *string* in some deployments; this helper
    normalizes to a Python dict.
    """
    path = "/weekly_sumup_fae/table/list"
    url = urllib.parse.urljoin(session.base_url, path)
    data = urllib.parse.urlencode(
        {
            "id": user_id,
            "departmentid": department_id,
            "date": report_date,
            "workType": str(work_type),
            "fetchAll": fetch_all,
        }
    ).encode("utf-8")
    req = urllib.request.Request(url=url, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with session.opener.open(req, timeout=120) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"table/list did not return JSON. First 400 chars: {raw[:400]}") from exc
    return payload


def sumup_rows_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    block = payload.get("sumup")
    if not isinstance(block, dict):
        return []
    data = block.get("data")
    if not isinstance(data, list):
        return []
    return [r for r in data if isinstance(r, dict)]


def row_has_substantive_content(row: dict[str, Any]) -> bool:
    if str(row.get("statement") or "").strip():
        return True
    try:
        return float(row.get("workTime") or 0) >= 0.5
    except (TypeError, ValueError):
        return False


def count_substantive_sumups(payload: dict[str, Any]) -> int:
    return sum(1 for r in sumup_rows_from_payload(payload) if row_has_substantive_content(r))


def build_sumup_row_for_save(row: dict[str, Any], label: str, week_num: str) -> dict[str, Any]:
    """Map ``table/list`` / Vue row to ``save_report`` sumup JSON (DOM field names)."""
    pid = row.get("projectId")
    if pid is None:
        pid = 0
    wt = row.get("workType")
    wt_str = str(int(wt)) if wt not in (None, "") else ""
    work_time = row.get("workTime")
    return {
        "id": str(row.get("id") or ""),
        "label": label,
        "weekNum": week_num,
        "sequence": row.get("sequence"),
        "statement": row.get("statement") or "",
        "workTime": "" if work_time in (None, "") else str(work_time),
        "workType.id": wt_str,
        "project.id": pid,
        "jiraId": row.get("jiraId") or "无",
        "notes": row.get("notes") or "",
        "isOnTime": bool(row.get("isOnTime", True)),
        "reason.id": "",
    }


def build_issue_plan_rows_for_save(
    rows: list[dict[str, Any]], label: str, week_num: str
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if not str(row.get("statement") or "").strip():
            continue
        item: dict[str, Any] = {"label": label, "weekNum": week_num, "sequence": row.get("sequence")}
        for key in ("statement", "suggest", "isSolve", "needAssist", "id"):
            if key in row:
                item[key] = row[key]
        out.append(item)
    return out


def copy_last_week_and_save(
    session: AatsSession,
    user_id: str,
    department_id: str,
    target_label: str | None = None,
    *,
    zone: str = "Europe/Istanbul",
) -> dict[str, Any]:
    """
    Copy last week (``table/list`` at ``target - 7 days``), POST ``save_report``, re-read and verify.

    Returns a result dict with ``ok``, ``target_label``, ``source_label``, ``save_response``,
    ``verify_rows``, ``substantive``, ``already_filled``.
    """
    target = (target_label or filing_week_label_iso(zone)).strip()
    source = previous_report_date(target)
    week_num = iso_week_number_str(target)

    current = post_table_list(session, user_id, department_id, target)
    substantive_before = count_substantive_sumups(current)
    if substantive_before > 0:
        return {
            "ok": True,
            "already_filled": True,
            "target_label": target,
            "source_label": source,
            "calendar_today": calendar_today_iso(zone),
            "save_response": "",
            "verify_rows": len(sumup_rows_from_payload(current)),
            "substantive": substantive_before,
        }

    prev_payload = post_table_list(session, user_id, department_id, source)
    sumups, issues, plans = build_copy_last_week_rows(prev_payload, target)
    save_sumups = [r for r in sumups if row_has_substantive_content(r)]
    if not save_sumups:
        return {
            "ok": False,
            "already_filled": False,
            "target_label": target,
            "source_label": source,
            "calendar_today": calendar_today_iso(zone),
            "save_response": "",
            "verify_rows": 0,
            "substantive": 0,
            "error": "No substantive rows in previous week to copy.",
        }

    save_rows = [build_sumup_row_for_save(r, target, week_num) for r in save_sumups]
    issue_rows = build_issue_plan_rows_for_save(issues, target, week_num)
    plan_rows = build_issue_plan_rows_for_save(plans, target, week_num)

    save_response = save_report(
        session,
        sumup_json=json.dumps(save_rows, ensure_ascii=False),
        issue_json=json.dumps(issue_rows, ensure_ascii=False),
        plan_json=json.dumps(plan_rows, ensure_ascii=False),
    )
    if save_response.strip() != "success":
        return {
            "ok": False,
            "already_filled": False,
            "target_label": target,
            "source_label": source,
            "calendar_today": calendar_today_iso(zone),
            "save_response": save_response,
            "verify_rows": 0,
            "substantive": 0,
            "error": f"save_report returned {save_response!r}",
        }

    verify = post_table_list(session, user_id, department_id, target)
    substantive = count_substantive_sumups(verify)
    return {
        "ok": substantive > 0,
        "already_filled": False,
        "target_label": target,
        "source_label": source,
        "calendar_today": calendar_today_iso(zone),
        "save_response": save_response,
        "verify_rows": len(sumup_rows_from_payload(verify)),
        "substantive": substantive,
        "copied_rows": len(save_rows),
    }


def save_report(
    session: AatsSession,
    *,
    sumup_json: str,
    issue_json: str = "[]",
    plan_json: str = "[]",
    remove_sumup: str = "",
    remove_issue: str = "",
    remove_plan: str = "",
) -> str:
    """
    POST /weekly_sumup_fae/save_report (same shape as the Vue/jQuery UI).

    Body uses application/x-www-form-urlencoded with JSON strings for sumup,
    issue, and plan. Response is typically the plain text ``success`` or a
    short error / session message.
    """
    path = "/weekly_sumup_fae/save_report"
    url = urllib.parse.urljoin(session.base_url, path)
    fields = {
        "sumup": sumup_json,
        "issue": issue_json,
        "plan": plan_json,
        "removeSumup": remove_sumup,
        "removeIssue": remove_issue,
        "removePlan": remove_plan,
    }
    body = urllib.parse.urlencode(fields).encode("utf-8")
    req = urllib.request.Request(url=url, data=body, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    req.add_header("X-Requested-With", "XMLHttpRequest")
    req.add_header("Referer", urllib.parse.urljoin(session.base_url, "/weekly_sumup_fae/main"))
    try:
        with session.opener.open(req, timeout=120) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"save_report HTTP {exc.code}: {detail[:4000]}") from exc


def open_aats(base_url: str) -> AatsSession:
    """Construct a session with a fresh cookie jar."""
    base = base_url.rstrip("/") + "/"
    return AatsSession(base_url=base, opener=build_opener())
