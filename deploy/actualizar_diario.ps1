# deploy/actualizar_diario.ps1
#
# Daily automatic update of the production VM (owner decision, 2026-10-14; same
# pattern as Central de Reportes' deploy\windows\actualizar_diario.ps1 and the
# Wansoft repo's Wansoft_Update_Repo_Diario). It fetches GitHub, and only when
# main has new commits it runs deploy\update.ps1 (pull, dependencies,
# migrations, sucursal + budget sync, static files, server restart). Nothing
# new: it logs that and exits, the server is not touched. Everything goes to
# logs\update.log.
#
# Registered by deploy\registrar_tarea_actualizacion.ps1 as
# "ControlPresupuestos_AP - Actualizar" (daily 04:30, between the monthly
# catalog task at 04:00 and the Gastos reales sync at 05:00).
#
# ASCII only on purpose: Windows PowerShell 5.1 reads .ps1 files as ANSI.

$ProjectDir = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $ProjectDir "logs"
New-Item -ItemType Directory -Force $LogDir | Out-Null
$Log = Join-Path $LogDir "update.log"
$SafeDir = $ProjectDir -replace '\\', '/'

function Escribir([string]$msg) {
    Add-Content -Path $Log -Value ("{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg)
}

Set-Location $ProjectDir
git -c "safe.directory=$SafeDir" fetch origin main 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) { Escribir "FAILED: git fetch (exit $LASTEXITCODE)"; exit 1 }
$Local = (git -c "safe.directory=$SafeDir" rev-parse HEAD).Trim()
$Remoto = (git -c "safe.directory=$SafeDir" rev-parse origin/main).Trim()
if ($Local -eq $Remoto) {
    Escribir ("No changes ({0})" -f $Local.Substring(0, 7))
    exit 0
}

Escribir ("Updating {0} -> {1}" -f $Local.Substring(0, 7), $Remoto.Substring(0, 7))
$env:GIT_CONFIG_COUNT = "1"  # safe.directory for update.ps1's own git pull
$env:GIT_CONFIG_KEY_0 = "safe.directory"
$env:GIT_CONFIG_VALUE_0 = $SafeDir
# A separate process with its output to files: in Windows PowerShell 5.1,
# redirecting it here would turn git's progress on stderr into errors that stop
# update.ps1 ($ErrorActionPreference = "Stop"). WaitForExit() and not -Wait:
# -Wait also waits for child processes, and update.ps1 leaves Waitress running.
# Files named per run: Waitress may inherit and keep a handle open.
$Marca = Get-Date -Format "yyyyMMdd_HHmmss"
$Salida = Join-Path $LogDir "update_$Marca.out.log"
$Errores = Join-Path $LogDir "update_$Marca.err.log"
$Proceso = Start-Process powershell.exe -PassThru -NoNewWindow -WorkingDirectory $ProjectDir `
    -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$(Join-Path $ProjectDir 'deploy\update.ps1')`"" `
    -RedirectStandardOutput $Salida -RedirectStandardError $Errores
$null = $Proceso.Handle  # PowerShell 5.1 loses ExitCode unless the handle is read first
$Proceso.WaitForExit()
$Texto = Get-Content $Salida, $Errores -ErrorAction SilentlyContinue
$Texto | Add-Content -Path $Log
Escribir ("update.ps1 finished (exit {0})" -f $Proceso.ExitCode)
Get-ChildItem $LogDir -Filter "update_*.log" | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-30) } |
    Remove-Item -ErrorAction SilentlyContinue

# update.ps1 does not stop on a failing native command (migrate, a sync
# script), so its exit code alone does not prove the deploy worked. Check the
# code landed, the server answers, and no step printed a Python traceback.
$Ahora = (git -c "safe.directory=$SafeDir" rev-parse HEAD).Trim()
if ($Ahora -ne $Remoto) { Escribir "FAILED: the code did not reach origin/main, check the output above"; exit 1 }
if ($Texto -match "WARNING: port") { Escribir "FAILED: the server does not answer after the update, check logs\waitress.err.log"; exit 1 }
if ($Texto -match "Traceback \(most recent call last\)") { Escribir "FAILED: a step printed a Python traceback, check the output above"; exit 1 }
Escribir ("Done at {0}" -f $Ahora.Substring(0, 7))
