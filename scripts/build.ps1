<#
.SYNOPSIS
  Construieste FocusDesk Windows x64, onedir implicit (onefile optional).
  Datele si setarile utilizatorului nu se copiaza in distributie.
#>
param(
    [switch]$OneFile,
    [string]$Python = "",
    [string]$OutDir = (Join-Path $env:LOCALAPPDATA "focusdesk-build"),
    [switch]$SkipTests,
    [switch]$SkipSmoke
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
if (-not $Python) {
    $venv = Join-Path $env:LOCALAPPDATA "focusdesk-venv\Scripts\python.exe"
    $Python = if (Test-Path $venv) { $venv } else { "python" }
}
& $Python -c "import sys, struct; assert sys.platform == 'win32' and sys.version_info >= (3, 11) and struct.calcsize('P') == 8, 'Foloseste Python x64 pe Windows'; import PyInstaller, ttkbootstrap, pydantic, portalocker, icalendar, tzdata, openpyxl, win32com.client; print('Dependente OK')"
if ($LASTEXITCODE -ne 0) { throw 'Instaleaza dependentele: pip install -e .[dev]' }
if (-not (Test-Path "src\focusdesk\resources\focusdesk.ico")) {
    & $Python scripts/make_icon.py
    if ($LASTEXITCODE -ne 0) { throw 'Generarea pictogramei a esuat.' }
}
if (-not $SkipTests) {
    & $Python -m pytest -q -p no:cacheprovider
    if ($LASTEXITCODE -ne 0) { throw 'Testele au esuat; build oprit.' }
}
$env:FOCUSDESK_ONEFILE = $(if ($OneFile) { "1" } else { "" })
$dist = Join-Path $OutDir 'dist'
$work = Join-Path $OutDir 'work'
& $Python -m PyInstaller --noconfirm --clean --distpath $dist --workpath $work focusdesk.spec
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller a esuat.' }
$bundleRoot = if ($OneFile) { $dist } else { Join-Path $dist 'FocusDesk' }
$licenses = Join-Path $bundleRoot 'licenses'
& $Python scripts/collect_distribution_licenses.py $licenses
if ($LASTEXITCODE -ne 0) { throw 'Colectarea licentelor a esuat.' }
Copy-Item 'src/focusdesk/resources/icons/LICENSE.txt' (Join-Path $licenses 'FocusDesk-icons-MIT.txt')
# Git is optional: source ZIP downloads have no .git directory.
$commit = 'source-archive'
if ((Test-Path (Join-Path $root '.git')) -and (Get-Command git -ErrorAction SilentlyContinue)) {
    $revision = & git rev-parse HEAD
    if ($LASTEXITCODE -eq 0) { $commit = $revision }
}
$pythonVersion = & $Python -c 'import platform; print(platform.python_version())'
@{ platform = 'Windows-x64'; python = $pythonVersion; commit = $commit } | ConvertTo-Json | Set-Content -Encoding utf8 (Join-Path $bundleRoot 'build-info.json')
@"
FocusDesk — Windows x64
Extrage complet folderul FocusDesk si porneste FocusDesk.exe.
Nu necesita Python sau alte instalari pentru functiile locale.
Outlook Classic este optional: calendar, ciorne si trimitere manuala cu confirmare.
New Outlook nu ofera COM. Evenimentele sunt rezervari personale de timp.
Workspace-ul se alege separat. Setarile raman in %APPDATA%/FocusDesk.
Actualizare: inchide aplicatia, extrage noua versiune intr-un folder separat,
apoi redeschide workspace-ul existent. Nu inlocui folderul de date.
Licente: licenses/. Executabilul nu este semnat digital.
"@ | Set-Content -Encoding utf8 (Join-Path $bundleRoot 'CITESTE-MA.txt')
$exe = if ($OneFile) { Join-Path $dist 'FocusDesk.exe' } else { Join-Path $bundleRoot 'FocusDesk.exe' }
if (-not $SkipSmoke) {
    & $Python scripts/verify_distribution.py --exe $exe --reports (Join-Path $OutDir 'verification')
    if ($LASTEXITCODE -ne 0) { throw 'Verificarea executabilului a esuat.' }
}
Write-Host "Gata: $exe"
