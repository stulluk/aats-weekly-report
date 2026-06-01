# host-pc (VPN workstation)

Scripts expect **AATS to be reachable** (FortiClient VPN on your laptop unless you use a direct `AATS_BASE_URL`).

For the full story (save pitfalls, date trap, Host PC vs Dumpling), see the root [`README.md`](../README.md).

## Reader

```bash
cd /path/to/aats-weekly-report
export AML_USER=... AML_PWD=...
python3 host-pc/scripts/aats_read_weekly_report.py
```

See the root `README.md` for HTTP vs browser notes.

## Weekly copy + save + verify + ntfy (Fri/Sat/Sun 11:00 Istanbul)

Goal: **copy last week → save → verify** substantive **sumup** rows for the filing week, then **always** POST a summary to ntfy. On your PC, optionally show **notify-send**. If the week is already filled, skip save and report OK.

1. Copy `host-pc/systemd/aats-weekly-notify.env.example` to `~/.config/aats-weekly-notify.env`, fill `REPO_ROOT`, credentials, `AATS_BASE_URL`, and **`NTFY_URL`** (same topic path on every host), e.g. `https://ntfy.kernelmax.com/aats-weekly-sumup-fae`. Set `AATS_NOTIFY_DESKTOP=1` for GNOME/KDE pop-ups. `chmod 600 ~/.config/aats-weekly-notify.env`.

2. Symlink or copy the unit files from `host-pc/systemd/` into `~/.config/systemd/user/` (adjust paths if you prefer another layout):

   ```bash
   ln -sf "$REPO_ROOT/host-pc/systemd/aats-weekly-filled-check.service" ~/.config/systemd/user/
   ln -sf "$REPO_ROOT/host-pc/systemd/aats-weekly-filled-check.timer" ~/.config/systemd/user/
   systemctl --user daemon-reload
   systemctl --user enable --now aats-weekly-filled-check.timer
   systemctl --user list-timers | grep aats
   ```

3. **VPN:** FortiClient is still yours to start. With **`AATS_VPN_PREFLIGHT=1`** in the env file, `aats_notify_check.sh` does a quick `curl` to `AATS_BASE_URL/weekly_sumup_fae/main` first; if it fails, it posts an **urgent** ntfy and exits `3` (same pattern as aml-tpm-weekly “no VPN / no route”). Dumpling should **not** set this variable.

4. **Report date:** By default scripts use **`filing_week_label_iso`** (upcoming Sunday write-date in Europe/Istanbul). Override with **`AATS_REPORT_DATE`** in the env file or `--date YYYY-MM-DD` when debugging. See root README “Date trap”.

5. **Desktop pop-up under systemd --user:** `notify-send` needs a session bus and often **`DISPLAY`** (e.g. `:0`). If nothing appears, add a drop-in override, for example `systemctl --user edit aats-weekly-filled-check.service`:

   ```ini
   [Service]
   Environment=DISPLAY=:0
   ```

6. Manual test:

   ```bash
   set -a && source ~/.config/aats-weekly-notify.env && set +a
   bash "${REPO_ROOT}/host-pc/scripts/aats_notify_check.sh"
   ```

Checker alone: `python3 host-pc/scripts/aats_check_weekly_filled.py --date YYYY-MM-DD`
