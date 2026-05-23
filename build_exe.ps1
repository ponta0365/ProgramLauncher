param(
    [switch]$Clean
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

if ($Clean) {
    Remove-Item '.\build' -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item '.\dist' -Recurse -Force -ErrorAction SilentlyContinue
}

python -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --name ProgramLauncher `
    --onedir `
    --hidden-import PySide6.QtCore `
    --hidden-import PySide6.QtGui `
    --hidden-import PySide6.QtWidgets `
    .\main.py

$DistRoot = Join-Path $Root 'dist\ProgramLauncher'
$LicenseRoot = Join-Path $DistRoot 'licenses'
New-Item -ItemType Directory -Path $LicenseRoot -Force | Out-Null

Copy-Item '.\README.md' -Destination $DistRoot -Force
Copy-Item '.\ProgramLauncher.bat' -Destination $DistRoot -Force
Copy-Item '.\THIRD_PARTY_NOTICES.txt' -Destination $DistRoot -Force
if (Test-Path '.\LICENSE') {
    Copy-Item '.\LICENSE' -Destination $DistRoot -Force
}
if (Test-Path '.\LICENSE.txt') {
    Copy-Item '.\LICENSE.txt' -Destination $DistRoot -Force
}

$PyInstallerLicense = @"
import importlib.metadata as m
from pathlib import Path

dist = m.distribution('PyInstaller')
base = Path(dist.locate_file('.'))
for rel in dist.files or []:
    rel_path = Path(rel)
    if rel_path.name.lower() == 'copying.txt':
        print(base / rel_path)
        break
"@ | python -

$PyInstallerLicense = ($PyInstallerLicense | Select-Object -First 1).Trim()
if ($PyInstallerLicense -and (Test-Path $PyInstallerLicense)) {
    Copy-Item $PyInstallerLicense -Destination (Join-Path $LicenseRoot 'PyInstaller-COPYING.txt') -Force
}

Write-Host "Build completed: $DistRoot"
