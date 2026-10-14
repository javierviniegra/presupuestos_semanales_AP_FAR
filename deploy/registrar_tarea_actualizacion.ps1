# deploy/registrar_tarea_actualizacion.ps1
#
# Registers (or replaces) the daily-update Windows Scheduled Task on the
# production VM. Run it once, in an ADMINISTRATOR PowerShell, from the project
# folder; safe to run again (-Force replaces the task).
#
#   "ControlPresupuestos_AP - Actualizar": every day at 04:30, runs
#   deploy\actualizar_diario.ps1, which fetches GitHub and runs
#   deploy\update.ps1 only when main has new commits (log: logs\update.log).
#
# It runs as the current user with logon type S4U: whether or not anyone is
# logged on, without storing a password (it only needs the network: GitHub,
# Odoo and MySQL). Same setup as the Central de Reportes update task.
#
# ASCII only on purpose: Windows PowerShell 5.1 reads .ps1 files as ANSI.

$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent $PSScriptRoot
$Usuario = "$env:USERDOMAIN\$env:USERNAME"
$Principal = New-ScheduledTaskPrincipal -UserId $Usuario -LogonType S4U -RunLevel Highest
$Ajustes = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)

$Accion = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$(Join-Path $ProjectDir 'deploy\actualizar_diario.ps1')`"" `
    -WorkingDirectory $ProjectDir
$Diario = New-ScheduledTaskTrigger -Daily -At "04:30"
Register-ScheduledTask -TaskName "ControlPresupuestos_AP - Actualizar" -Action $Accion -Trigger $Diario `
    -Principal $Principal -Settings $Ajustes -Force | Out-Null

Get-ScheduledTask -TaskName "ControlPresupuestos_AP - Actualizar" | Format-Table TaskName, State -AutoSize
Write-Host "Done. Daily at 04:30. Log: logs\update.log (full output of each run: logs\update_<date>.*.log)."
