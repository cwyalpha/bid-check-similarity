$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$EnvName = "checksim_py38"
$Python = "C:\Users\cwyal\anaconda3\envs\$EnvName\python.exe"
$AppName = -join (0x6807, 0x4E66, 0x6587, 0x4EF6, 0x67E5, 0x91CD, 0x5DE5, 0x5177 | ForEach-Object { [char]$_ })

if (-not (Test-Path $Python)) {
    Write-Host "Conda environment '$EnvName' not found. Create it first:" -ForegroundColor Yellow
    Write-Host "  conda create -n $EnvName python=3.8 -y"
    exit 1
}

& $Python -m pip install -r requirements-win38.txt

Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name $AppName `
    --collect-submodules docx `
    --collect-submodules PIL `
    --hidden-import win32com.client `
    --hidden-import pythoncom `
    --hidden-import pywintypes `
    run_app.py

Write-Host "Build complete: dist\$AppName.exe" -ForegroundColor Green
