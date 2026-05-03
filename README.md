# aats-weekly-report

Automation helpers for **AATS** (`weekly_sumup_fae` on `aats.amlogic.com`), split like other weekly tooling:

| Layout | Use when |
| --- | --- |
| `host-pc/` | Your workstation is on **corporate VPN** (or otherwise can reach AATS) and you want interactive checks / future schedulers tied to FortiClient + `systemd --user`. |
| `dumpling/` | Reserved for **headless** scheduling (e.g. user `crontab` on `us-build-dumpling`) without FortiClient; same HTTP approach, different env defaults (later). |

Shared HTTP helpers live in `scripts/` (Python 3, stdlib only).

---

## Reader (no browser): “Did I file anything this week?”

**Script:** `host-pc/scripts/aats_read_weekly_report.py`

**Order of operations (same idea as the browser):** you must **log in first**, then the tool loads the weekly shell and calls **`table/list`** for the chosen report date. There is no separate “anonymous read” of your draft; the session cookie from login is required.

It:

1. `POST /weekly_sumup_fae/user/login/ad` with `AML_USER` / `AML_PWD` (same semantics as the web “Email” tab: user name may omit `@amlogic.com`).
2. `GET /weekly_sumup_fae/main` and parses embedded JS for your **`id`**, **`departmentid`**, and default **`write-date`**.
3. `POST /weekly_sumup_fae/table/list` with that metadata and the report date.
4. Prints a **short text summary** of `sumup` / `issue` / `plan` rows (or `--dump-json` for the full payload).

### How we verify together

1. **VPN on** (this repo’s tools assume AATS is reachable from your PC unless you override `AATS_BASE_URL`).
2. Pick the **same report date** as in the browser (`write-date` field on the weekly form).
3. Run:

```bash
cd /media/KINGDATA/DREJO-PROJECTS/aats-weekly-report
export AML_USER=... AML_PWD=...
python3 host-pc/scripts/aats_read_weekly_report.py
# or explicit date:
python3 host-pc/scripts/aats_read_weekly_report.py --date 2026-04-26
```

4. Open AATS in the browser for that date and **compare row count and task text** with the script output.
5. Optional deep check: add `--dump-json` once, confirm JSON matches what you see after “Save”.

If the reader shows rows for that date, you **did have saved data** for that report week (at least what `table/list` returns). If it shows zero rows, either nothing was saved for that date or the date does not match the UI week.

---

## curl / HTTP vs browser automation

- **Reading** (what you asked first): **Yes, plain HTTP is enough** — the SPA still exposes classic form login and `$.ajax` endpoints (`table/list`). No Playwright required for the reader.
- **Writing / Save**: The UI builds a payload in JavaScript and `POST`s to `/weekly_sumup_fae/save_report` with `sumup`, `issue`, `plan` as **JSON strings** plus remove-* keys. In principle **curl can submit the same POST** if you reproduce that JSON exactly (including `project.id`, overdue reason ids, validation rules). The fragile parts are **Vue treeselect / dynamic rows** and server-side validation; a browser driver is more forgiving but heavier.
- **Practical split**: use **HTTP** for login + read + id discovery; add either **carefully crafted curl** or **Playwright** only for submit once the payload is stable.

### Comment / “Others” text field

In the `table/list` JSON, the free-text comment for a row (including **Others**)
is stored under **`notes`**, not `statement` (which is the main task line).

Experimental writer: `host-pc/scripts/aats_try_append_sumup_notes.py`. A first
server trial returned **HTTP 500** (`WeeklySumup.getWorkType()` null), which
means the **save JSON shape still does not match** what the Spring controller
expects—capture a real **Save** request from the browser (copy as **fetch** /
**curl**) and align field names / nesting, or drive the UI with Playwright.

---

## Environment variables

| Variable | Meaning |
| --- | --- |
| `AML_USER` | Login user (email tab); `@amlogic.com` appended when missing. |
| `AML_PWD` | Password for the same login. |
| `AATS_BASE_URL` | Optional override; default **`http://aats.amlogic.com`**. |

Never commit real credentials. Use a local env file or your shell profile.

---

## dumpling/

Not wired yet. Planned: same Python modules, **no FortiClient gate**, scheduling via **`crontab`**, and ntfy defaults aligned with what works from the build network (often `https://ntfy.sh`).
