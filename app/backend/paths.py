"""统一的路径定义。打包后仍然能正确解析到 exe 同级目录。"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent.parent
MEIPASS_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR)).resolve()
RUNTIME_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else APP_DIR
DATA_DIR = RUNTIME_DIR

CONFIG_FILE = DATA_DIR / "pollution_config.json"
SAVE_FILE = DATA_DIR / "pollution_count.json"
OCR_POSITION_FILE = DATA_DIR / "ocr_capture_positions.json"
CONFIG_EXAMPLE_NAME = "pollution_config.example.json"
SAVE_EXAMPLE_NAME = "pollution_count.example.json"

RECORD_DIR = DATA_DIR / "records"
RECORD_JSONL = RECORD_DIR / "shiny_records.jsonl"
RECORD_CSV = RECORD_DIR / "shiny_records.csv"
TODAY_ARCHIVE_JSONL = RECORD_DIR / "today_cleared_archive.jsonl"
TODAY_ARCHIVE_CSV = RECORD_DIR / "today_cleared_archive.csv"

ICON_CANDIDATES = ("roco_counter_icon.ico",)


def resolve_resource_path(name: str) -> Path:
    """在 MEIPASS / RUNTIME / APP 三个根目录依次查找资源。"""
    for root in (MEIPASS_DIR, RUNTIME_DIR, APP_DIR):
        candidate = Path(root) / name
        if candidate.exists():
            return candidate
    return Path(name)


def seed_runtime_file(target: Path, example_name: str, fallback_text: str | None = None) -> None:
    """若运行时文件缺失，则优先用仓库/打包内的 example 文件初始化。"""
    if target.exists():
        return

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        return

    example = resolve_resource_path(example_name)
    try:
        if example.exists() and example.resolve() != target.resolve():
            shutil.copy2(example, target)
            return
    except Exception:
        pass

    if fallback_text is None:
        return

    try:
        target.write_text(fallback_text, encoding="utf-8")
    except Exception:
        pass


def find_icon() -> Path | None:
    for name in ICON_CANDIDATES:
        p = resolve_resource_path(name)
        if p.exists():
            return p
    return None
