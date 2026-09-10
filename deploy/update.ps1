# deploy/update.ps1
#
# Run this by hand on the production VM whenever there's a new version to
# deploy. Pulls the latest code from GitHub, installs any new dependencies,
# applies migrations, refreshes static files, then restarts the server.
#
# First-time setup (cloning the repo, creating the venv, .env, initial
# migrate/createsuperuser) is NOT part of this script - see
# deploy/PRODUCTION_SETUP.md for that, once.
#
# Assumes: this file lives at <project_root>\deploy\update.ps1, the venv is
# at <project_root>\.venv, and Waitress is used to serve the app (no
# IIS/nginx in front - WhiteNoise serves static files directly).

$ErrorActionPreference = "Stop"

# Port this app listens on on this VM. XAMPP already uses 80/443/3306 here,
# and other Python/Gradio apps use their own ports - pick one that's free
# and keep it consistent across deploys.
$Port = 8020

$ProjectDir = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectDir ".venv\Scripts\python.exe"
$WaitressExe = Join-Path $ProjectDir ".venv\Scripts\waitress-serve.exe"
$LogsDir = Join-Path $ProjectDir "logs"
New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null

Set-Location $ProjectDir

Write-Host "=== Pulling latest code from GitHub ==="
git pull origin main

Write-Host "=== Installing/updating dependencies ==="
& $Python -m pip install -r requirements.txt

Write-Host "=== Applying database migrations ==="
& $Python manage.py migrate --noinput

Write-Host "=== Syncing sucursales from Odoo ==="
# Idempotent (get_or_create by odoo_company_id) - safe on every deploy,
# including the very first one. Without this, a brand-new environment has
# zero Sucursal rows and scheduler.py silently skips every GastoReal line
# (no matching Sucursal to attach it to) instead of erroring loudly.
& $Python scripts\sync_sucursales.py

Write-Host "=== Collecting static files ==="
& $Python manage.py collectstatic --noinput

Write-Host "=== Stopping the currently running server (if any) ==="
Get-Process waitress-serve -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -eq $WaitressExe } |
    Stop-Process -Force
Start-Sleep -Seconds 1

Write-Host "=== Starting the server on port $Port ==="
$stdOut = Join-Path $LogsDir "waitress.out.log"
$stdErr = Join-Path $LogsDir "waitress.err.log"
Start-Process -FilePath $WaitressExe `
    -ArgumentList "--host=0.0.0.0", "--port=$Port", "config.wsgi:application" `
    -WorkingDirectory $ProjectDir `
    -WindowStyle Hidden `
    -RedirectStandardOutput $stdOut `
    -RedirectStandardError $stdErr

Start-Sleep -Seconds 3
$listening = Test-NetConnection -ComputerName 127.0.0.1 -Port $Port -WarningAction SilentlyContinue
if ($listening.TcpTestSucceeded) {
    Write-Host "=== Done. Server is listening on port $Port. ==="
} else {
    Write-Host "=== WARNING: port $Port is not responding yet. Check $stdErr for errors. ==="
}
