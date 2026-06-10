from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable


IS_WINDOWS = os.name == "nt"

if IS_WINDOWS:
    try:
        import pythoncom  # type: ignore[import-not-found]
    except ImportError:
        pythoncom = None  # type: ignore[assignment]
    try:
        import win32com.client  # type: ignore[import-not-found]
    except ImportError:
        win32com = None  # type: ignore[assignment]
else:
    pythoncom = None  # type: ignore[assignment]
    win32com = None  # type: ignore[assignment]


LogCallback = Callable[[str], None]

RE_SAFE_NAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')


class LegacyConversionError(RuntimeError):
    """Raised when .doc/.wps conversion is not available or failed."""


def convert_legacy_to_docx(
    input_path: str | Path,
    log: LogCallback | None = None,
    soffice_path: str | None = None,
    timeout: int = 120,
) -> tuple[Path, Path]:
    """Convert .doc/.wps to .docx and return (docx_path, temp_dir).

    The caller owns temp_dir and should remove it after parsing.
    """

    source = Path(input_path).expanduser().resolve()
    suffix = source.suffix.lower()
    if suffix not in {".doc", ".wps"}:
        raise ValueError(f"仅支持转换 .doc/.wps 文件: {source}")

    work_dir = Path(tempfile.mkdtemp(prefix="checksim_legacy_"))
    target = work_dir / f"{_safe_stem(source)}.docx"
    errors: list[str] = []

    try:
        if IS_WINDOWS:
            for prog_id, label in _windows_com_candidates():
                try:
                    _log(log, f"  > 尝试使用 {label} 转换 {source.name}...")
                    _convert_with_com(source, target, prog_id)
                    if target.exists() and target.stat().st_size > 0:
                        _log(log, f"  > {label} 转换完成。")
                        return target, work_dir
                    errors.append(f"{label}: 未生成 docx 文件")
                except Exception as exc:
                    errors.append(f"{label}: {exc}")
                    _remove_partial(target)

            try:
                _convert_with_soffice(source, target, log, soffice_path, timeout, work_dir)
                return target, work_dir
            except Exception as exc:
                errors.append(f"LibreOffice: {exc}")
        else:
            try:
                _convert_with_soffice(source, target, log, soffice_path, timeout, work_dir)
                return target, work_dir
            except Exception as exc:
                errors.append(f"LibreOffice: {exc}")

        detail = "；".join(str(item) for item in errors if str(item).strip())
        if IS_WINDOWS:
            message = (
                f"无法自动转换 {source.name}。已按 WPS、Microsoft Office、LibreOffice 顺序尝试，"
                "但都不可用或转换失败。请安装 WPS/Office/LibreOffice，或先手动另存为 .docx 后再导入。"
            )
        else:
            message = (
                f"无法自动转换 {source.name}。macOS/Linux 下需要安装 LibreOffice 并确保 soffice 可用，"
                "或先手动另存为 .docx 后再导入。"
            )
        if detail:
            message += f" 详细信息：{detail}"
        raise LegacyConversionError(message)
    except Exception:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise


def find_soffice(explicit_path: str | None = None) -> str | None:
    if explicit_path:
        expanded = Path(explicit_path).expanduser()
        if expanded.is_file():
            return str(expanded)

    for executable in ("soffice", "soffice.com", "libreoffice"):
        found = shutil.which(executable)
        if found:
            return found

    common_paths: list[str] = []
    if sys.platform == "darwin":
        common_paths.extend(
            [
                "/Applications/LibreOffice.app/Contents/MacOS/soffice",
                "/opt/homebrew/bin/soffice",
                "/usr/local/bin/soffice",
            ]
        )
    elif IS_WINDOWS:
        for base in (os.environ.get("PROGRAMFILES"), os.environ.get("PROGRAMFILES(X86)")):
            if base:
                common_paths.extend(
                    [
                        os.path.join(base, "LibreOffice", "program", "soffice.com"),
                        os.path.join(base, "LibreOffice", "program", "soffice.exe"),
                    ]
                )
    else:
        common_paths.extend(
            [
                "/usr/bin/soffice",
                "/usr/local/bin/soffice",
                "/usr/bin/libreoffice",
                "/usr/local/bin/libreoffice",
                "/snap/bin/libreoffice",
                "/opt/libreoffice/program/soffice",
                "/opt/libreoffice*/program/soffice",
            ]
        )

    for candidate in common_paths:
        if "*" in candidate:
            for path in sorted(Path("/").glob(candidate.lstrip("/"))):
                if path.is_file():
                    return str(path)
        elif candidate and Path(candidate).is_file():
            return candidate
    return None


def _windows_com_candidates() -> list[tuple[str, str]]:
    return [
        ("KWPS.Application", "WPS"),
        ("WPS.Application", "WPS"),
        ("Word.Application", "Microsoft Office"),
    ]


def _convert_with_com(source: Path, target: Path, prog_id: str) -> None:
    if win32com is None:
        raise RuntimeError("pywin32 未安装，无法使用 WPS/Office COM。")

    initialized = False
    if pythoncom is not None:
        pythoncom.CoInitialize()
        initialized = True

    app = None
    document = None
    try:
        app = win32com.client.DispatchEx(prog_id)  # type: ignore[union-attr]
        try:
            app.Visible = False
            app.DisplayAlerts = 0
        except Exception:
            pass
        document = app.Documents.Open(str(source), ReadOnly=1)
        document.SaveAs2(str(target), FileFormat=12)
    finally:
        if document is not None:
            try:
                document.Close(False)
            except Exception:
                pass
        if app is not None:
            try:
                app.Quit()
            except Exception:
                pass
        if initialized and pythoncom is not None:
            pythoncom.CoUninitialize()


def _convert_with_soffice(
    source: Path,
    target: Path,
    log: LogCallback | None,
    soffice_path: str | None,
    timeout: int,
    work_dir: Path,
) -> None:
    soffice = find_soffice(soffice_path)
    if not soffice:
        raise RuntimeError("未检测到 LibreOffice soffice。")

    out_dir = work_dir / "soffice_out"
    profile_dir = work_dir / "soffice_profile"
    out_dir.mkdir(parents=True, exist_ok=True)
    profile_dir.mkdir(parents=True, exist_ok=True)

    _log(log, f"  > 尝试使用 LibreOffice 转换 {source.name}...")
    cmd = [
        soffice,
        "--headless",
        "--norestore",
        f"-env:UserInstallation={profile_dir.resolve().as_uri()}",
        "--convert-to",
        "docx",
        "--outdir",
        str(out_dir),
        str(source),
    ]

    creationflags = 0
    if IS_WINDOWS and hasattr(subprocess, "CREATE_NO_WINDOW"):
        creationflags = subprocess.CREATE_NO_WINDOW

    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=max(10, int(timeout or 120)),
            creationflags=creationflags,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"LibreOffice 转换超时 ({timeout}s)。") from exc
    except FileNotFoundError as exc:
        raise RuntimeError(f"找不到 soffice 可执行文件: {soffice}") from exc

    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"LibreOffice 转换失败: {detail}")

    generated = _find_generated_docx(out_dir, source)
    if not generated:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"LibreOffice 未生成 docx 文件。{detail}")

    shutil.copy2(generated, target)
    _log(log, "  > LibreOffice 转换完成。")


def _find_generated_docx(out_dir: Path, source: Path) -> Path | None:
    generated = sorted(out_dir.glob("*.docx"))
    if not generated:
        return None
    for path in generated:
        if path.stem.lower() == source.stem.lower():
            return path
    return generated[0]


def _safe_stem(path: Path) -> str:
    stem = RE_SAFE_NAME.sub("_", path.stem).strip(" ._")
    return (stem or "legacy_document")[:80]


def _remove_partial(path: Path) -> None:
    try:
        if path.exists():
            path.unlink()
    except OSError:
        pass


def _log(log: LogCallback | None, message: str) -> None:
    if log:
        log(message)
