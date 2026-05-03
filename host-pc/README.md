# host-pc (VPN workstation)

Scripts here expect **AATS to be reachable** (typically FortiClient VPN on your laptop).

## Reader

```bash
cd /path/to/aats-weekly-report
export AML_USER=... AML_PWD=...
python3 host-pc/scripts/aats_read_weekly_report.py
```

See the root `README.md` for verification steps and HTTP vs browser notes.
