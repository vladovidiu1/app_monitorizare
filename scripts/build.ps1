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
    [switch]$SkipTests,
    [string]$ModelPath = "",
    [switch]$LinkModel,
    [switch]$SkipSmoke
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not $Python) {
    $venv = Join-Path $env:LOCALAPPDATA "focusdesk-venv\Scripts\python.exe"
    $Python = if (Test-Path $venv) { $venv } else { "python" }
}
Write-Host "Python: $Python"
& $Python -c "import sys, struct, llama_cpp; assert sys.platform == 'win32' and sys.version_info[:2] == (3, 12) and struct.calcsize('P') == 8, 'Build AI: foloseste Python 3.12 x64 pe Windows'; assert llama_cpp.__version__ == '0.3.36'; from focusdesk.ai.models import read_manifest; read_manifest().require_verified(); print('AI CPU si manifest OK')"
if ($LASTEXITCODE -ne 0) { throw "Instaleaza requirements-ai.txt cu Python 3.12 x64; verifica manifestul modelului." }

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

# License and attribution are delivered alongside the executable, also for onefile.
# Never embed the 5 GB GGUF into the executable or its temporary extraction directory.
$bundleRoot = if ($OneFile) { $dist } else { Join-Path $dist "FocusDesk" }
$licenses = Join-Path $bundleRoot "licenses"
# A clean onedir is mandatory for the downloadable distribution.
& $Python scripts/collect_distribution_licenses.py $licenses
if ($LASTEXITCODE -ne 0) { throw "License collection failed." }
Copy-Item "packaging/licenses/*" $licenses -Force
Copy-Item "src/focusdesk/resources/icons/LICENSE.txt" (Join-Path $licenses "FocusDesk-icons-MIT.txt")
$info = @{ platform = "Windows-x64"; python = "3.12"; cpu_only = $true; model_included = [bool]$ModelPath; commit = (& git rev-parse HEAD) }
$info | ConvertTo-Json | Set-Content -Encoding utf8 (Join-Path $bundleRoot "build-info.json")
@"
FocusDesk — Windows x64, CPU
Dezarhiveaza complet folderul FocusDesk si porneste FocusDesk.exe.
Nu necesita Python, Ollama, CUDA sau server AI. Model: models/ langa executabil.
Outlook Classic este optional, numai pentru integrarea Outlook; New Outlook nu ofera COM.
Workspace-ul se alege separat. Setarile raman in %APPDATA%/FocusDesk.
Actualizari: inchide aplicatia, extrage noua versiune intr-un folder separat;
redeschide workspace-ul existent. Pachetul fara model necesita pastrarea models/.
Licente si atribuire: licenses/. Nu muta modelul in workspace.
"@ | Set-Content -Encoding utf8 (Join-Path $bundleRoot "CITESTE-MA.txt")
New-Item -ItemType Directory -Force -Path $licenses | Out-Null
Copy-Item "src\focusdesk\resources\Qwen3-LICENSE.txt" $licenses
Copy-Item "src\focusdesk\resources\Qwen3-MODEL-CARD.md" $licenses
Copy-Item "src\focusdesk\resources\ai-model.json" $licenses
Copy-Item "docs\AI.md" $licenses
New-Item -ItemType Directory -Force -Path (Join-Path $bundleRoot "models") | Out-Null
if ($ModelPath) {
    # Developer prepares a complete offline distribution; end users do not run Python.
    $resolvedModel = (Resolve-Path $ModelPath).Path
    & $Python -c "import sys; from pathlib import Path; from focusdesk.ai.models import read_manifest, verify_file, validate_location; verify_file(validate_location(Path(sys.argv[1])), read_manifest())" $resolvedModel
    if ($LASTEXITCODE -ne 0) { throw "Modelul nu corespunde manifestului; distributia nu este completa." }
    $manifest = Get-Content "src\focusdesk\resources\ai-model.json" -Raw | ConvertFrom-Json
    $targetModel = Join-Path $bundleRoot ("models\" + $manifest.filename)
    if ($LinkModel) {
        # Same-volume NTFS hardlink: cache + bundle share the same 5 GB, avoiding a disk explosion.
        if (Test-Path $targetModel) { Remove-Item $targetModel }
        New-Item -ItemType HardLink -Path $targetModel -Target $resolvedModel | Out-Null
    } else { Copy-Item $resolvedModel $targetModel -Force }
}

$exe = if ($OneFile) { Join-Path $dist "FocusDesk.exe" } else { Join-Path $dist "FocusDesk\FocusDesk.exe" }
if (-not $SkipSmoke -and $ModelPath) {
    & $Python scripts\verify_distribution.py --exe $exe --reports (Join-Path $OutDir "verification")
} elseif (-not $SkipSmoke) {
    & $Python scripts\verify_ai_exe.py --exe $exe
}
if ($LASTEXITCODE -ne 0) { throw "Verificarea executabilului AI a esuat." }
Write-Host "Gata: $exe"
