$ErrorActionPreference = "Stop"

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
  throw "Python not found: $python. Create .venv and install requirements.txt first."
}

& $python -m PyInstaller `
  --noconfirm `
  --clean `
  --onefile `
  --noconsole `
  --name C4NetAutonomy `
  --add-data "app\static;app\static" `
  desktop.py

Write-Host "Build complete: dist\C4NetAutonomy.exe"
