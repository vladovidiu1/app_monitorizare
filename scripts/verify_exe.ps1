<#
.SYNOPSIS
  Verificare de fum a executabilului: porneste FocusDesk.exe pe un workspace demonstrativ temporar, asteapta
  fereastra principala, face o captura DOAR a ferestrei lui (PrintWindow) si il inchide.
.NOTES
  Nu este o verificare pe un calculator fara Python; ruleaza cu PATH curatat de Python doar ca aproximare.
#>
param(
    [string]$Exe = (Join-Path $env:LOCALAPPDATA "focusdesk-build\dist\FocusDesk\FocusDesk.exe"),
    [string]$Shot = (Join-Path $env:LOCALAPPDATA "Temp\focusdesk_exe.png"),
    [int]$WaitSeconds = 8
)
$ErrorActionPreference = "Stop"
if (-not (Test-Path $Exe)) { throw "Nu exista: $Exe" }

$py = Join-Path $env:LOCALAPPDATA "focusdesk-venv\Scripts\python.exe"
$ws = Join-Path ([System.IO.Path]::GetTempPath()) ("fd_exe_" + [guid]::NewGuid().ToString("N").Substring(0, 8) + "\demo")
& $py -c "import sys; sys.path.insert(0, 'src'); from pathlib import Path; from focusdesk.services.demo import create_demo_workspace; create_demo_workspace(Path(r'$ws'))"
if ($LASTEXITCODE -ne 0) { throw "Nu s-a putut crea workspace-ul demo" }

Add-Type -ReferencedAssemblies System.Drawing @"
using System; using System.Drawing; using System.Runtime.InteropServices;
public class WinShot {
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint flags);
  public static void Capture(IntPtr h, string path) {
    RECT r; GetWindowRect(h, out r);
    int w = r.Right - r.Left, hgt = r.Bottom - r.Top;
    using (Bitmap bmp = new Bitmap(w, hgt))
    using (Graphics g = Graphics.FromImage(bmp)) {
      IntPtr hdc = g.GetHdc();
      PrintWindow(h, hdc, 2);
      g.ReleaseHdc(hdc);
      bmp.Save(path, System.Drawing.Imaging.ImageFormat.Png);
    }
  }
}
"@

# PATH fara Python, ca aproximare a unui calculator fara Python
$env:PATH = ($env:PATH -split ";" | Where-Object { $_ -and ($_ -notmatch "(?i)python") }) -join ";"
$env:PYTHONHOME = $null; $env:PYTHONPATH = $null
# Configuratia aplicatiei (%APPDATA%\FocusDesk) ramane izolata, ca testul sa nu modifice setarile reale.
$env:APPDATA = Join-Path ([System.IO.Path]::GetTempPath()) ("fd_appdata_" + [guid]::NewGuid().ToString("N").Substring(0, 8))
New-Item -ItemType Directory -Path $env:APPDATA | Out-Null
$p = Start-Process -FilePath $Exe -ArgumentList @("--workspace", $ws) -PassThru
$deadline = (Get-Date).AddSeconds($WaitSeconds)
$handle = [IntPtr]::Zero
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Milliseconds 500
    $p.Refresh()
    if ($p.HasExited) { throw "FocusDesk.exe s-a inchis (cod $($p.ExitCode))." }
    if ($p.MainWindowHandle -ne [IntPtr]::Zero -and $p.MainWindowTitle -like "FocusDesk*") { $handle = $p.MainWindowHandle; break }
}
if ($handle -eq [IntPtr]::Zero) { Stop-Process -Id $p.Id -Force; throw "Fereastra principala nu a aparut in $WaitSeconds s." }
Start-Sleep -Seconds 2
[WinShot]::Capture($handle, $Shot)
Write-Host "Titlu fereastra: $($p.MainWindowTitle)"
Write-Host "Captura: $Shot"
$exeDir = Split-Path $Exe
$strayData = Get-ChildItem $exeDir -Recurse -Filter "workspace.json" -ErrorAction SilentlyContinue
Write-Host ("Date in folderul executabilului: " + $(if ($strayData) { "DA (problema!)" } else { "nu" }))
Stop-Process -Id $p.Id -Force
Write-Host "OK: executabilul a pornit si a deschis workspace-ul demo."
