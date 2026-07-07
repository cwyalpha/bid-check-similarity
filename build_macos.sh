#!/usr/bin/env bash
set -euo pipefail

APP_NAME="标书文件查重工具"
PYTHON_BIN="${CHECKSIM_PYTHON:-python3}"
VENV_DIR="${CHECKSIM_MACOS_VENV:-.venv-macos}"

"${PYTHON_BIN}" -m venv "${VENV_DIR}"
# shellcheck source=/dev/null
source "${VENV_DIR}/bin/activate"

python -m pip install --upgrade pip setuptools wheel
python -m pip install -e . pyinstaller

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

python -m PyInstaller \
  --noconfirm \
  --clean \
  --windowed \
  --name "${APP_NAME}" \
  --collect-submodules docx \
  --collect-submodules PIL \
  run_app.py

rm -f "release/${ASSET_NAME}"
/usr/bin/ditto -c -k --sequesterRsrc --keepParent "dist/${APP_NAME}.app" "release/${ASSET_NAME}"

echo "Build complete: release/${ASSET_NAME}"
