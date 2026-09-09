# Production setup

Two machines are involved:

- **App VM** (`SVR-HIKCENTER`, internal IP `192.168.100.93`): runs this
  app. **Waitress** serves it directly on its own port, no IIS/nginx in
  front; **WhiteNoise** serves static files from inside the app itself.
- **Proxy/DB server** (`187.251.203.223`): already runs MySQL (used for
  this app's production database) and an Apache reverse proxy on port
  `8088` that maps URL paths to other internal apps (`/mba/`, `/tba/`,
  ...). This app is added to that same proxy under `/presupuestos_ap/`.

End users reach the app at `http://187.251.203.223:8088/presupuestos_ap/`
- never directly at the app VM's own address/port.

After the one-time setup below, day-to-day updates on the app VM are just
[`deploy/update.ps1`](update.ps1) - see the bottom of this file.

## 1. Prerequisites on the app VM

- Python 3.12+ and Git, both on `PATH`. On a fresh Windows 11 VM neither
  is there by default, and there's a decoy: `python`/`git` may appear to
  "exist" via the Microsoft Store's app-execution-alias stub (a fake
  `python.exe` that just opens the Store) - if `python --version` prints
  nothing useful or errors instead of a real version, install for real via
  `winget install --id Python.Python.3.12 -e --source winget` and
  `winget install --id Git.Git -e --source winget`, then in **Settings ->
  Advanced app settings -> App execution aliases**, turn OFF `python.exe`
  and `python3.exe` so the real install takes over. Open a **new**
  PowerShell window afterward (PATH doesn't refresh in an already-open one).
- If `.venv\Scripts\activate` refuses to run
  ("running scripts is disabled on this system"), run once:
  `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`
  (needed for `update.ps1` too, not just venv activation).
- Read access to this GitHub repo (Git Credential Manager, bundled with
  Git for Windows, prompts a browser login on the first `git clone`/`pull`
  against a private repo - no separate token needed unless that fails).

## 2. Clone the repo and create the virtualenv

```powershell
cd C:\Apps
git clone https://github.com/javierviniegra/presupuestos_semanales_AP_FAR.git ControlPresupuestos_AP
cd ControlPresupuestos_AP
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## 3. Production database (on the proxy/DB server, 187.251.203.223)

Confirm the app VM can actually reach it first:

```powershell
Test-NetConnection -ComputerName 187.251.203.223 -Port 3306
```

`TcpTestSucceeded : True` means it's reachable. Create the database and a
dedicated user for this app (via phpMyAdmin on that server, or a MySQL
client) - **not** `root`, and **not** shared with another app's database:

```sql
CREATE DATABASE presupuestos_ap CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'presupuestosusers'@'%' IDENTIFIED BY 'CHOOSE_A_REAL_PASSWORD';
GRANT ALL PRIVILEGES ON presupuestos_ap.* TO 'presupuestosusers'@'%';
FLUSH PRIVILEGES;
```

(`'%'` as the host because the connection comes from a different machine
than the DB server itself - `'localhost'` would refuse it.)

## 4. Configure `.env` (on the app VM)

```powershell
copy core\config\.env.example core\config\.env
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
notepad core\config\.env
```

```ini
ENV=prod
DJANGO_SECRET_KEY=<paste what the command above printed - never reuse dev's>
DJANGO_DEBUG=false
DJANGO_ALLOWED_HOSTS=187.251.203.223,192.168.100.93,localhost,127.0.0.1

# This app is reverse-proxied under a path prefix (see step 5) - without
# this, Django's own generated links (static files, admin, login
# redirects) would come out missing "/presupuestos_ap" and 404 through
# the proxy. Confirmed working end-to-end in dev before writing this.
DJANGO_FORCE_SCRIPT_NAME=/presupuestos_ap

PRESUPUESTOS_DB_HOST=187.251.203.223
PRESUPUESTOS_DB_PORT=3306
PRESUPUESTOS_DB_USER=presupuestosusers
PRESUPUESTOS_DB_PASSWORD=<the password from step 3>
PRESUPUESTOS_DB_NAME=presupuestos_ap

ODOO_URL=<same Odoo instance as dev>
ODOO_DB_NAME=<...>
ODOO_USER=<...>
ODOO_PASSWORD=<...>
```

Leave the `_DEV` variables blank - they're only read when `ENV=dev`.

## 5. Reverse proxy on 187.251.203.223 (Apache, port 8088)

Add a block to that server's `httpd-vhosts.conf`, inside the existing
`<VirtualHost *:8088>` alongside `/mba/` and `/tba/`:

```apache
# Presupuestos AP
ProxyPass /presupuestos_ap/ http://192.168.100.93:8020/
ProxyPassReverse /presupuestos_ap/ http://192.168.100.93:8020/
```

Also add a redirect so visiting the path *without* a trailing slash still
lands correctly (`ProxyPass` only matches the `.../` form):

```apache
RedirectMatch ^/presupuestos_ap$ /presupuestos_ap/
```

Restart Apache on that server after saving. `ProxyPreserveHost On` (already
set at the top of that `VirtualHost` block) is what makes
`DJANGO_ALLOWED_HOSTS=187.251.203.223` above work - Apache forwards the
original `Host` header instead of substituting the app VM's own address.

Why this needs `DJANGO_FORCE_SCRIPT_NAME` (step 4) and not just the proxy
rule alone: Apache strips the `/presupuestos_ap` prefix before forwarding,
so the app itself is genuinely mounted at its own root - but without
`FORCE_SCRIPT_NAME`, every link *Django generates* (static files, admin
pages, the login redirect) would still come out unprefixed and 404 once
the browser tries to follow them back through the proxy. `FORCE_SCRIPT_NAME`
makes Django prepend the prefix to everything it generates, while
WhiteNoise (serving static files) is specifically written to un-prefix its
own matching so the two halves agree. Verified locally end-to-end before
writing this (static files load, and an unauthenticated `/dashboard/`
redirects to a correctly single-prefixed `/presupuestos_ap/accounts/login/`).

## 6. Migrate, create an admin user, collect static files (app VM)

```powershell
python manage.py migrate
python manage.py createsuperuser
python manage.py collectstatic --noinput
```

## 7. First launch (app VM)

```powershell
.\deploy\update.ps1
```

Starts Waitress in the background on port `8020` (change that at the top
of `update.ps1` if it's already taken by something else on this VM) and
logs to `logs\waitress.out.log` / `logs\waitress.err.log`.

Confirm it's up locally first: `Test-NetConnection 127.0.0.1 -Port 8020`
on the app VM. Then, once step 5's Apache block is in place, confirm the
real path end users will use:
`http://187.251.203.223:8088/presupuestos_ap/`.

## 8. Keeping GastoReal/catalog data in sync (optional, same as dev)

If this production instance should also pull data from Odoo on its own
schedule, register the same three Windows Scheduled Tasks used on the dev
machine, pointed at this VM's own paths:

```powershell
$venvPython = "C:\Apps\ControlPresupuestos_AP\.venv\Scripts\python.exe"
$projectDir = "C:\Apps\ControlPresupuestos_AP"
$currentUser = "$env:USERDOMAIN\$env:USERNAME"

Register-ScheduledTask -TaskName "ControlPresupuestos_AP - Gastos reales AM" `
  -Action (New-ScheduledTaskAction -Execute $venvPython -Argument "scripts\scheduler.py" -WorkingDirectory $projectDir) `
  -Trigger (New-ScheduledTaskTrigger -Daily -At 5:00AM) -User $currentUser -Force

Register-ScheduledTask -TaskName "ControlPresupuestos_AP - Gastos reales PM" `
  -Action (New-ScheduledTaskAction -Execute $venvPython -Argument "scripts\scheduler.py" -WorkingDirectory $projectDir) `
  -Trigger (New-ScheduledTaskTrigger -Daily -At 2:00PM) -User $currentUser -Force

schtasks /Create /TN "ControlPresupuestos_AP - Catalogos mensual" `
  /TR "$projectDir\scripts\run_classify_odoo_catalog.bat" /SC MONTHLY /D 1 /ST 04:00 /F
```

Only do this if production should sync independently from dev - if dev's
schedule already feeds the same production database, skip this section
entirely to avoid syncing twice.

## Known limitation: does not survive a VM reboot on its own

`update.ps1` starts Waitress as a plain background process. If the app VM
restarts, nothing brings it back automatically - someone has to run
`deploy\update.ps1` again by hand. If that's not acceptable, the two ways
to fix it (not set up yet, ask if you want either):

- A Windows Scheduled Task with an "At startup" trigger that runs
  `deploy\update.ps1`.
- Wrapping Waitress as a real Windows Service (e.g. via NSSM), which also
  restarts it automatically if the process crashes, not just on reboot.
