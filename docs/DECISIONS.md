# Decisions

Newest first. Each entry: what, why, and where it applies.

## 2026-10-14 - Production updates itself every day

- **Owner:** production should update by itself every day, like Wansoft (`Wansoft_Update_Repo_Diario`) and Central de Reportes, instead of someone running `deploy\update.ps1` by hand after every push. Before this the app VM only had "Arranque automatico" (runs `update.ps1` when the VM starts) and the one-time "Actualizacion unica" used on 2026-10-06 (no longer needed, can be deleted).
- **What:** the scheduled task **"ControlPresupuestos_AP - Actualizar"** runs `deploy\actualizar_diario.ps1` every day at **04:30**. It does a `git fetch`; only when `origin/main` has new commits it runs `deploy\update.ps1` (pull, dependencies, migrations, sucursal and budget sync, static files, server restart). With nothing new it logs "No changes" and exits: the server is not touched and nobody sees a restart.
- **Why 04:30:** it leaves 30 minutes after the monthly catalog task (day 1, 04:00, which runs a full GastoReal sync) and lands before the Gastos reales sync (05:00 and 14:00), so a restart does not fall in the middle of a sync and what was pushed the day before is live before the 05:00 run uses it.
- **How it runs (same rules as Central de Reportes' `actualizar_diario.ps1`):**
  - `update.ps1` runs in a separate process (`Start-Process -PassThru` + `WaitForExit()`) with its output going to per-run files (`logs\update_<date>.out.log` / `.err.log`, kept 30 days). Not `-Wait`: it also waits for child processes and `update.ps1` leaves Waitress running, so the task would never finish. No `2>&1` in the same process: in Windows PowerShell 5.1 it turns git's progress text on stderr into errors, which stop `update.ps1` (`$ErrorActionPreference = "Stop"`).
  - Everything is summarized in `logs\update.log`; the full output of each update is appended to it.
  - The `.ps1` files are ASCII only (Windows PowerShell 5.1 reads them as ANSI).
  - `safe.directory` is passed to git (command line and environment), so it works whichever account the task runs as.
- **Added on top of Central's script:** `update.ps1` does not stop when a native command fails (a failing `migrate` or sync script just prints and the script goes on), so its exit code alone proves nothing. After the update the script marks the run **FAILED** in `logs\update.log` if the code did not reach `origin/main`, if `update.ps1` printed its "port is not responding" warning, or if any step printed a Python traceback. A FAILED run exits with code 1, so Task Scheduler shows it as a failed run too.
- **Known limit:** the task only deploys when there is a new commit. If an update fails *after* the pull, the next day's fetch finds no new commits and does not retry: the FAILED line is the signal, and the fix is to correct the cause and run `deploy\update.ps1` by hand.
- **Registration:** once, in an administrator PowerShell on the app VM, after `git pull`: `.\deploy\registrar_tarea_actualizacion.ps1` (see `deploy/PRODUCTION_SETUP.md`, section 9). The task runs as the current user with logon type S4U: it runs whether or not anyone is logged on, without storing a password.
- **Where it applies:** the production app VM only. Dev is updated by hand (`git pull` + `runserver 8010`).
