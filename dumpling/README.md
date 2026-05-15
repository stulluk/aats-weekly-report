# dumpling (headless server)

No FortiClient; scheduling is plain **`crontab`**. Use the same **topic** path as on your PC: `aats-weekly-sumup-fae`.

## Friday 08:30 — AATS filled check + ntfy (no desktop)

1. Ensure this repo is cloned on dumpling and Python 3 is available.

2. Put secrets in a root-only file, for example `/root/.config/aats-weekly-notify.env`:

   ```bash
   install -d -m 700 /root/.config
   cp /path/to/aats-weekly-report/host-pc/systemd/aats-weekly-notify.env.example /root/.config/aats-weekly-notify.env
   # edit: REPO_ROOT, AML_*, AATS_BASE_URL (often internal), NTFY_URL=https://ntfy.sh/aats-weekly-sumup-fae
   # omit AATS_NOTIFY_DESKTOP or set to 0
   chmod 600 /root/.config/aats-weekly-notify.env
   ```

3. **Crontab** — **Europe/Istanbul** 08:30 Friday (same wall clock intent as the laptop timer):

   ```cron
   30 8 * * 5 TZ=Europe/Istanbul set -a && . /root/.config/aats-weekly-notify.env && set +a && export AATS_NOTIFY_DESKTOP=0 AATS_VPN_PREFLIGHT=0 && exec /bin/bash "${REPO_ROOT}/host-pc/scripts/aats_notify_check.sh"
   ```

4. Confirm dumpling can reach `AATS_BASE_URL` **without** Forti (internal DNS or IP). If it cannot, the check will exit `1` and ntfy will still get an error message.
