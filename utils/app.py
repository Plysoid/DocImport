from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

APP_NAME = "DocImport"
APP_VERSION = "4.1.0-beta1"


def app_dir() -> Path:
    """Folder where the app/exe is located."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def rel_path(*parts: str) -> Path:
    return app_dir().joinpath(*parts)


def ensure_dirs() -> None:
    for name in ("data", "input", "output", "logs", "tesseract"):
        rel_path(name).mkdir(parents=True, exist_ok=True)


def clean_logs() -> None:
    logs = rel_path("logs")
    if logs.exists():
        for item in logs.iterdir():
            try:
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
            except PermissionError:
                pass
    logs.mkdir(parents=True, exist_ok=True)


def configure_tesseract() -> None:
    """Use portable tesseract\tesseract.exe if it exists near the app."""
    try:
        import pytesseract
    except Exception:
        return

    exe = rel_path("tesseract", "tesseract.exe")
    tessdata = rel_path("tesseract", "tessdata")

    if exe.exists():
        pytesseract.pytesseract.tesseract_cmd = str(exe)

    if tessdata.exists():
        os.environ["TESSDATA_PREFIX"] = str(tessdata)
