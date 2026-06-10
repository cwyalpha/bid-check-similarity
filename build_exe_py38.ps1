$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$EnvName = "checksim_py38"
$AppName = -join (0x6807, 0x4E66, 0x6587, 0x4EF6, 0x67E5, 0x91CD, 0x5DE5, 0x5177 | ForEach-Object { [char]$_ })

function Invoke-BuildPython {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    if ($env:CHECKSIM_PYTHON) {
        $Python = Get-Command $env:CHECKSIM_PYTHON -ErrorAction SilentlyContinue
        if ($Python) {
            & $Python.Source @Arguments
            return
        }
        Write-Host "CHECKSIM_PYTHON is set but not found: $env:CHECKSIM_PYTHON" -ForegroundColor Yellow
    }

    $Conda = Get-Command conda -ErrorAction SilentlyContinue
    if ($Conda) {
        & $Conda.Source run -n $EnvName python @Arguments
        return
    }

    Write-Host "Python runtime not found." -ForegroundColor Yellow
    Write-Host "Set CHECKSIM_PYTHON to a Python 3.8 executable, or create the default conda environment:" -ForegroundColor Yellow
    Write-Host "  conda create -n $EnvName python=3.8 -y"
    exit 1
}

Invoke-BuildPython @("-m", "pip", "install", "-r", "requirements-win38.txt")

Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
Invoke-BuildPython @(
    "-m", "PyInstaller",
    "--noconfirm",
    "--clean",
    "--onefile",
    "--windowed",
    "--name", $AppName,
    "--collect-submodules", "docx",
    "--collect-submodules", "PIL",
    "--hidden-import", "win32com.client",
    "--hidden-import", "pythoncom",
    "--hidden-import", "pywintypes",
    "run_app.py"
)

Write-Host "Build complete: dist\$AppName.exe" -ForegroundColor Green
