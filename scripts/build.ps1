<#
.SYNOPSIS
  Construieste FocusDesk pentru Windows cu PyInstaller (onedir implicit, onefile optional).
.PARAMETER OneFile
  Construieste un singur .exe (porneste mai lent; foloseste un director temporar pentru dezarhivare).
.PARAMETER Python
  Interpretorul cu dependentele instalate (implicit: venv-ul din %LOCALAPPDATA%\focusdesk-venv, apoi `python`).
.PARAMETER OutDir
  Unde se scriu dist/ si work/. Implicit in afara folderului proiectului (evita sincronizarea OneDrive).
#>
param(
    [switch]$OneFile,
    [string]$Python = "",
    [string]$OutDir = (Join-Path $env:LOCALAPPDATA "focusdesk-build"),
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not $Python) {
    $venv = Join-Path $env:LOCALAPPDATA "focusdesk-venv\Scripts\python.exe"
    $Python = if (Test-Path $venv) { $venv } else { "python" }
}
Write-Host "Python: $Python"

& $Python -c "import PyInstaller, ttkbootstrap, pydantic, portalocker, icalendar, tzdata; print('dependente OK')"
if ($LASTEXITCODE -ne 0) { throw "Instaleaza dependentele: pip install -e .[dev]" }

if (-not (Test-Path "src\focusdesk\resources\focusdesk.ico")) { & $Python scripts\make_icon.py }
if (-not $SkipTests) {
    & $Python -m pytest -q -p no:cacheprovider
    if ($LASTEXITCODE -ne 0) { throw "Testele au esuat; build oprit." }
}

$env:FOCUSDESK_ONEFILE = $(if ($OneFile) { "1" } else { "" })
$dist = Join-Path $OutDir "dist"
$work = Join-Path $OutDir "work"
& $Python -m PyInstaller --noconfirm --clean --distpath $dist --workpath $work focusdesk.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller a esuat." }

$exe = if ($OneFile) { Join-Path $dist "FocusDesk.exe" } else { Join-Path $dist "FocusDesk\FocusDesk.exe" }
Write-Host "Gata: $exe"
