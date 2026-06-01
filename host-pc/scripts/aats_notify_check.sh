#!/usr/bin/env bash
# Copy last week → SAVE → verify substantive rows → ntfy (always).
#
# Required: REPO_ROOT, AML_USER, AML_PWD, NTFY_URL
# Optional: AATS_BASE_URL, AATS_REPORT_DATE (target write-date), AATS_VPN_PREFLIGHT=1 (host PC),
#           AATS_NOTIFY_DESKTOP=1, AATS_SKIP_SAVE=1 (check-only legacy path)

set -u
export TZ="${TZ:-Europe/Istanbul}"

: "${REPO_ROOT:?Set REPO_ROOT to your aats-weekly-report checkout}"
: "${AML_USER:?}"
: "${AML_PWD:?}"
: "${NTFY_URL:?Set NTFY_URL to e.g. https://ntfy.sh/aats-weekly-sumup-fae}"

BASE_URL="${AATS_BASE_URL:-http://aats.amlogic.com}"
PY_SAVE="${REPO_ROOT}/host-pc/scripts/aats_weekly_copy_save_verify.py"
export PYTHONPATH="${REPO_ROOT}/scripts${PYTHONPATH:+:${PYTHONPATH}}"

date_args=()
if [[ -n "${AATS_REPORT_DATE:-}" ]]; then
  date_args=(--date "${AATS_REPORT_DATE}")
fi

META="$(python3 -c "from aats_http import calendar_today_iso, filing_week_label_iso, previous_report_date; z='Europe/Istanbul'; t=filing_week_label_iso(z); print(f'{calendar_today_iso(z)}|{t}|{previous_report_date(t)}')")"
CALENDAR_TODAY="${META%%|*}"
rest="${META#*|}"
REPORT_DATE="${rest%%|*}"
COPY_SOURCE="${rest##*|}"

tmp_out="$(mktemp)"
tmp_err="$(mktemp)"
trap 'rm -f "${tmp_out}" "${tmp_err}"' EXIT

_send_ntfy() {
  local title="$1" priority="$2" body="$3"
  set +e
  printf '%s' "${body}" | curl -fsS -o /dev/null \
    -H "Title: ${title}" \
    -H "Priority: ${priority}" \
    -H "Tags: calendar" \
    --data-binary @- \
    "${NTFY_URL}"
  local c=$?
  set -e
  if [[ "${c}" -ne 0 ]]; then
    echo "ERROR: ntfy curl failed (exit ${c}) for ${NTFY_URL}" >&2
  fi
  return "${c}"
}

_desktop() {
  local title="$1" desk="$2"
  if [[ "${AATS_NOTIFY_DESKTOP:-0}" == "1" ]] && command -v notify-send >/dev/null 2>&1; then
    desk="${desk:0:600}"
    notify-send -u normal -- "${title}" "${desk}" 2>/dev/null || true
  fi
}

if [[ "${AATS_VPN_PREFLIGHT:-0}" == "1" ]]; then
  if ! curl -fsS --connect-timeout 6 --max-time 15 -o /dev/null "${BASE_URL}/weekly_sumup_fae/main"; then
    t="AATS unreachable (VPN / network)"
    b="GET ${BASE_URL}/weekly_sumup_fae/main failed. Target write-date would be ${REPORT_DATE}."
    _send_ntfy "${t}" "urgent" "${b}"
    _desktop "${t}" "${b}"
    exit 3
  fi
fi

if [[ "${AATS_SKIP_SAVE:-0}" == "1" ]]; then
  PY_CHECK="${REPO_ROOT}/host-pc/scripts/aats_check_weekly_filled.py"
  set +e
  summary="$(python3 "${PY_CHECK}" "${date_args[@]}" --base-url "${BASE_URL}" 2>"${tmp_err}")"
  rc=$?
  set -e
  if [[ "${rc}" -eq 0 ]]; then
    title="AATS OK — report ${REPORT_DATE} filled (check only)"
    priority="default"
  elif [[ "${rc}" -eq 2 ]]; then
    title="AATS empty — report ${REPORT_DATE} not filled (check only)"
    priority="high"
  else
    title="AATS check failed (${REPORT_DATE})"
    priority="urgent"
  fi
  body="Calendar today: ${CALENDAR_TODAY}
Write-date checked: ${REPORT_DATE}
Copy source would be: ${COPY_SOURCE}

${summary}"
  err_txt=""
  [[ -s "${tmp_err}" ]] && err_txt="$(head -c 3500 "${tmp_err}")"
  [[ -n "${err_txt}" ]] && body="${body}

${err_txt}"
  echo "${body}"
  _send_ntfy "${title}" "${priority}" "${body}" || exit $?
  exit "${rc}"
fi

set +e
python3 "${PY_SAVE}" "${date_args[@]}" --base-url "${BASE_URL}" >"${tmp_out}" 2>"${tmp_err}"
rc=$?
set -e

out_txt="$(cat "${tmp_out}")"
err_txt=""
[[ -s "${tmp_err}" ]] && err_txt="$(head -c 3500 "${tmp_err}")"

if [[ "${rc}" -eq 0 ]]; then
  if echo "${out_txt}" | grep -q '"already_filled": true'; then
    title="AATS OK — report ${REPORT_DATE} already saved"
    priority="default"
  else
    title="AATS OK — saved and verified (${REPORT_DATE})"
    priority="default"
  fi
elif [[ "${rc}" -eq 2 ]]; then
  title="AATS FAIL — save did not verify (${REPORT_DATE})"
  priority="urgent"
else
  title="AATS ERROR (${REPORT_DATE})"
  priority="urgent"
fi

body="Calendar today: ${CALENDAR_TODAY}
Write-date (AATS label): ${REPORT_DATE}
Copy candidate (target-7d): ${COPY_SOURCE}
Scan window: up to ${AATS_MAX_WEEKS_BACK:-4} prior week(s)

${out_txt}"
if [[ -n "${err_txt}" ]]; then
  body="${body}

${err_txt}"
fi

echo "title=${title} priority=${priority} rc=${rc}"
echo "${body}"

curl_rc=0
_send_ntfy "${title}" "${priority}" "${body}" || curl_rc=$?
_desktop "${title}" "$(echo "${out_txt}" | head -n 5)"

if [[ "${rc}" -ne 0 ]]; then
  exit "${rc}"
fi
exit "${curl_rc}"
