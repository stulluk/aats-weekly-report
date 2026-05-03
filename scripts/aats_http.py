"""
Minimal HTTP helpers for AATS (cookie jar, login, POST form).

English-only module for reuse by host-pc and dumpling tools.
"""

from __future__ import annotations

import http.cookiejar
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


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
    date_m = re.search(r'id="write-date"[^>]*value="([^"]+)"', html)
    write_date = date_m.group(1) if date_m else None
    return id_m.group(1), dep_m.group(1), write_date


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


def open_aats(base_url: str) -> AatsSession:
    """Construct a session with a fresh cookie jar."""
    base = base_url.rstrip("/") + "/"
    return AatsSession(base_url=base, opener=build_opener())
