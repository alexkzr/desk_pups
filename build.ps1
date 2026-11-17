$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
py -3 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
if ($LASTEXITCODE) { throw 'Dependency installation failed' }
& .\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onefile --windowed --hidden-import __future__ --name Takson main.py
if ($LASTEXITCODE) { throw 'Build failed' }
Write-Host 'Ready: dist\Takson.exe'
