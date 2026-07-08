$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$EnvName = "checksim_py38"
$AppName = -join (0x6807, 0x4E66, 0x6587, 0x4EF6, 0x67E5, 0x91CD, 0x5DE5, 0x5177 | ForEach-Object { [char]$_ })
$BundleOcr = if ($env:CHECKSIM_BUNDLE_OCR) { $env:CHECKSIM_BUNDLE_OCR } else { "1" }
$OcrModelDir = if ($env:CHECKSIM_OCR_MODEL_DIR) { $env:CHECKSIM_OCR_MODEL_DIR } else { "packaging\ocr_models" }

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

function Invoke-BuildPythonText {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    $Output = $null
    if ($env:CHECKSIM_PYTHON) {
        $Python = Get-Command $env:CHECKSIM_PYTHON -ErrorAction SilentlyContinue
        if ($Python) {
            $Output = & $Python.Source @Arguments
        }
    }
    else {
        $Conda = Get-Command conda -ErrorAction SilentlyContinue
        if ($Conda) {
            $Output = & $Conda.Source run -n $EnvName python @Arguments
        }
    }
    if ($null -eq $Output) {
        return ""
    }
    return ($Output | Where-Object { "$_".Trim() } | Select-Object -Last 1)
}

Invoke-BuildPython @("-m", "pip", "install", "-r", "requirements-win38.txt")
if ($BundleOcr -eq "1") {
    Invoke-BuildPython @("scripts\cache_ppocr_models.py", "--output", $OcrModelDir)
}

Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
$PyInstallerArgs = @(
    "-m", "PyInstaller",
    "--noconfirm",
    "--clean",
    "--onefile",
    "--windowed",
    "--name", $AppName,
    "--collect-submodules", "docx",
    "--collect-submodules", "PIL",
    "--collect-submodules", "pypdf"
)

if ($BundleOcr -eq "1") {
    $PyInstallerArgs += @(
        "--collect-all", "paddleocr",
        "--collect-all", "paddlex",
        "--collect-all", "onnxruntime",
        "--collect-all", "cv2",
        "--collect-all", "pypdfium2",
        "--collect-all", "imagesize",
        "--collect-all", "pyclipper",
        "--collect-all", "bidi",
        "--collect-all", "shapely",
        "--copy-metadata", "imagesize",
        "--copy-metadata", "opencv-contrib-python",
        "--copy-metadata", "pyclipper",
        "--copy-metadata", "pypdfium2",
        "--copy-metadata", "python-bidi",
        "--copy-metadata", "shapely",
        "--add-data", "$OcrModelDir;ocr_models"
    )
    $ShapelyGeosDll = Invoke-BuildPythonText @("-c", "from pathlib import Path; import shapely; root = Path(shapely.__file__).resolve().parent.parent / 'shapely.libs'; dlls = sorted(root.glob('geos_c*.dll')); print(dlls[0] if dlls else '')")
    if ($ShapelyGeosDll) {
        $PyInstallerArgs += @("--add-binary", "$ShapelyGeosDll;shapely.libs")
    }
}

$PyInstallerArgs += @(
    "--hidden-import", "win32com.client",
    "--hidden-import", "pythoncom",
    "--hidden-import", "pywintypes",
    "run_app.py"
)

$BuildPatchPath = (Resolve-Path "packaging\build_sitecustomize").Path
$PreviousPythonPath = $env:PYTHONPATH
if ($PreviousPythonPath) {
    $env:PYTHONPATH = "$BuildPatchPath;$PreviousPythonPath"
}
else {
    $env:PYTHONPATH = $BuildPatchPath
}
try {
    Invoke-BuildPython $PyInstallerArgs
}
finally {
    $env:PYTHONPATH = $PreviousPythonPath
}

Write-Host "Build complete: dist\$AppName.exe" -ForegroundColor Green
