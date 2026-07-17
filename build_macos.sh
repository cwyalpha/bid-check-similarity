#!/usr/bin/env bash
set -euo pipefail

APP_NAME="标书文件查重工具"
BUNDLE_OCR="${CHECKSIM_BUNDLE_OCR:-1}"
PYTHON_BIN="${CHECKSIM_PYTHON:-python3}"
VENV_DIR="${CHECKSIM_MACOS_VENV:-.venv-macos}"
OCR_MODEL_DIR="${CHECKSIM_OCR_MODEL_DIR:-packaging/ocr_models}"

if [[ -x "${VENV_DIR}/bin/python" ]]; then
  if ! "${VENV_DIR}/bin/python" - <<'PY' >/dev/null 2>&1
import sys
import tkinter

raise SystemExit(0 if sys.platform != "darwin" or tkinter.TkVersion >= 8.6 else 1)
PY
  then
    rm -rf "${VENV_DIR}"
  fi
fi

if [[ "${BUNDLE_OCR}" == "1" && -d "${VENV_DIR}" && ! -f "${VENV_DIR}/.checksim-bundle-ocr" ]]; then
  rm -rf "${VENV_DIR}"
fi
"${PYTHON_BIN}" -m venv "${VENV_DIR}"
# shellcheck source=/dev/null
source "${VENV_DIR}/bin/activate"

python -m pip install --upgrade pip setuptools wheel
python - <<'PY'
import sys
import tkinter

print(f"macOS build Python: {sys.executable} ({sys.version.split()[0]}), Tk {tkinter.TkVersion}")
if sys.platform == "darwin" and tkinter.TkVersion < 8.6:
    raise SystemExit(
        "Tk 8.6+ is required for the macOS GUI build. "
        "Set CHECKSIM_PYTHON to a Homebrew or Python.org python3."
    )
PY
if [[ "${BUNDLE_OCR}" == "1" ]]; then
  python -m pip install -e ".[ocr]" pyinstaller
  touch "${VENV_DIR}/.checksim-bundle-ocr"
  python scripts/cache_ppocr_models.py --output "${OCR_MODEL_DIR}"
else
  python -m pip install -e . pyinstaller
fi

VERSION="$(python - <<'PY'
from pathlib import Path
import re

text = Path("pyproject.toml").read_text(encoding="utf-8")
match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
if not match:
    raise SystemExit("Could not find project version in pyproject.toml")
print(match.group(1))
PY
)"
ARCH="$(uname -m)"
ASSET_NAME="BidCheckSimilarity-v${VERSION}-macOS-${ARCH}.zip"

rm -rf build "dist/${APP_NAME}.app"
mkdir -p release

PYINSTALLER_ARGS=(
  --noconfirm \
  --clean \
  --windowed \
  --name "${APP_NAME}" \
  --osx-bundle-identifier com.cwyalpha.bidchecksimilarity \
  --collect-submodules docx \
  --collect-submodules PIL \
  --collect-submodules pypdf \
)

if [[ "${BUNDLE_OCR}" == "1" ]]; then
  PYINSTALLER_ARGS+=(
    --collect-all paddleocr
    --collect-all paddlex
    --collect-all onnxruntime
    --collect-all cv2
    --collect-all pypdfium2
    --collect-all imagesize
    --collect-all pyclipper
    --collect-all bidi
    --collect-all shapely
    --copy-metadata imagesize
    --copy-metadata pyclipper
    --copy-metadata python-bidi
    --copy-metadata shapely
    --add-data "${OCR_MODEL_DIR}:ocr_models"
  )
fi

PYINSTALLER_ARGS+=(run_app.py)

python -m PyInstaller "${PYINSTALLER_ARGS[@]}"

INFO_PLIST="dist/${APP_NAME}.app/Contents/Info.plist"
if ! /usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString ${VERSION}" "${INFO_PLIST}"; then
  /usr/libexec/PlistBuddy -c "Add :CFBundleShortVersionString string ${VERSION}" "${INFO_PLIST}"
fi
if ! /usr/libexec/PlistBuddy -c "Set :CFBundleVersion ${VERSION}" "${INFO_PLIST}"; then
  /usr/libexec/PlistBuddy -c "Add :CFBundleVersion string ${VERSION}" "${INFO_PLIST}"
fi
codesign --force --deep --sign - "dist/${APP_NAME}.app"

rm -f "release/${ASSET_NAME}"
/usr/bin/ditto -c -k --sequesterRsrc --keepParent "dist/${APP_NAME}.app" "release/${ASSET_NAME}"

echo "Build complete: release/${ASSET_NAME}"
