#!/usr/bin/env bash
set -euo pipefail

APP_NAME="标书文件查重工具"
BUNDLE_OCR="${CHECKSIM_BUNDLE_OCR:-1}"
if [[ -z "${CHECKSIM_PYTHON:-}" && "${BUNDLE_OCR}" == "1" && -x /usr/bin/python3 ]]; then
  PYTHON_BIN="/usr/bin/python3"
else
  PYTHON_BIN="${CHECKSIM_PYTHON:-python3}"
fi
VENV_DIR="${CHECKSIM_MACOS_VENV:-.venv-macos}"
OCR_MODEL_DIR="${CHECKSIM_OCR_MODEL_DIR:-packaging/ocr_models}"

if [[ "${BUNDLE_OCR}" == "1" && -d "${VENV_DIR}" && ! -f "${VENV_DIR}/.checksim-bundle-ocr" ]]; then
  rm -rf "${VENV_DIR}"
fi
"${PYTHON_BIN}" -m venv "${VENV_DIR}"
# shellcheck source=/dev/null
source "${VENV_DIR}/bin/activate"

python -m pip install --upgrade pip setuptools wheel
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

rm -rf build dist
mkdir -p release

PYINSTALLER_ARGS=(
  --noconfirm \
  --clean \
  --windowed \
  --name "${APP_NAME}" \
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

PLIST_PATH="dist/${APP_NAME}.app/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Add :NSRequiresAquaSystemAppearance bool true" "${PLIST_PATH}" 2>/dev/null \
  || /usr/libexec/PlistBuddy -c "Set :NSRequiresAquaSystemAppearance true" "${PLIST_PATH}"

rm -f "release/${ASSET_NAME}"
/usr/bin/ditto -c -k --sequesterRsrc --keepParent "dist/${APP_NAME}.app" "release/${ASSET_NAME}"

echo "Build complete: release/${ASSET_NAME}"
