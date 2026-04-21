"""配置文件的默认值、加载与保存。"""

from __future__ import annotations

import json
from typing import Any, Dict

from .paths import CONFIG_EXAMPLE_NAME, CONFIG_FILE, seed_runtime_file
from .utils import build_builtin_resolution_presets


def _clone_default(value: Any) -> Any:
    return json.loads(json.dumps(value))


def _deep_fill_defaults(target: Dict[str, Any], defaults: Dict[str, Any]) -> None:
    for key, value in defaults.items():
        current = target.get(key)
        if key not in target:
            target[key] = _clone_default(value)
        elif isinstance(current, dict) and isinstance(value, dict):
            _deep_fill_defaults(current, value)


def _normalize_hotkey(value: Any) -> str:
    return str(value or "").strip().lower()

DEFAULT_CONFIG: Dict[str, Any] = {
    "middle_region": {"left": 1057, "top": 195, "width": 92, "height": 59},
    "header_region": {"left": 2125, "top": 30, "width": 372, "height": 150},
    "name_in_header": {"left": 99, "top": 35, "width": 204, "height": 48},
    "base_resolution": "2560x1600_150缩放",
    "active_resolution": "2560x1600_150缩放",
    "base_regions": {
        "middle_region": {"left": 1057, "top": 195, "width": 92, "height": 59},
        "header_region": {"left": 2125, "top": 30, "width": 372, "height": 150},
        "name_in_header": {"left": 99, "top": 35, "width": 204, "height": 48},
    },
    "resolution_presets": build_builtin_resolution_presets(),
    "cooldown_seconds": 12.0,
    "scan_interval": 0.7,
    "confirm_frames": 1,
    "window": {"x": 60, "y": 60, "width": 640, "height": 520},
    "compact_window": {"width": 260, "height": 200, "x": None, "y": None},
    "hotkeys": {"add": "8", "sub": "9", "start": "7", "pause": "", "lock": "-", "show_main": "0"},
    "unknown_species_name": "未识别",
    "always_on_top": True,
    "window_alpha": 1.0,
    "paddleocr_model_dir": "paddleocr_models",
    "middle_keyword": "力量",
    "middle_fallback_keywords": ["力量"],
    "middle_ocr_modes": [[3, "binary"], [3, "gray"], [4, "binary"], [3, "clahe"], [2, "gray"]],
    "middle_bright_threshold": 170,
    "middle_white_pixels_threshold": 45,
    "middle_bright_streak_required": 1,
    "middle_partial_confidence_threshold": 0.45,
    "middle_min_char_match_ratio": 0.5,
    "header_ocr_modes": [[4, "binary"], [3, "gray"]],
    "name_read_delay": 0.0,
    "app_version": "v1.2.5",
    "update_info_url": "https://raw.githubusercontent.com/YUZE04/Roco-pollution-counter/main/version.json",
    "github_api_latest_url": "https://api.github.com/repos/YUZE04/Roco-pollution-counter/releases/latest",
    "release_page_url": "https://github.com/YUZE04/Roco-pollution-counter/releases/latest",
    "overlay_locked": False,
    "overlay_alpha": 0.82,
    # OCR 误识别别名表：{OCR 结果: 真实名字}。默认修正一个已知误识别。
    # 真实精灵名是「噬光嗡嗡」，OCR 偶尔会读成「曙光瑜瑜」。
    "ocr_name_aliases": {
        "曙光瑜瑜": "噬光嗡嗡",
    },
}


def _migrate_hotkeys(cfg: Dict[str, Any]) -> None:
    hotkeys = cfg.get("hotkeys")
    if not isinstance(hotkeys, dict):
        cfg["hotkeys"] = _clone_default(DEFAULT_CONFIG["hotkeys"])
        return

    start_key = _normalize_hotkey(hotkeys.get("start"))
    pause_key = _normalize_hotkey(hotkeys.get("pause"))
    show_main_key = _normalize_hotkey(hotkeys.get("show_main"))

    # 兼容旧版本：曾经把“暂停/继续”藏在 pause 字段里，新版设置页只保留 start。
    if pause_key and not start_key and pause_key != show_main_key:
        hotkeys["start"] = pause_key
        start_key = pause_key

    # 避免隐藏的旧 pause 绑定与可见的新热键重复触发。
    if pause_key and pause_key in {start_key, show_main_key}:
        hotkeys["pause"] = ""


def _default_config_text() -> str:
    return json.dumps(_clone_default(DEFAULT_CONFIG), ensure_ascii=False, indent=2)


def load_config() -> Dict[str, Any]:
    seed_runtime_file(CONFIG_FILE, CONFIG_EXAMPLE_NAME, _default_config_text())
    if CONFIG_FILE.exists():
        try:
            cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            before = json.dumps(cfg, ensure_ascii=False, sort_keys=True)
            # 递归补齐缺失字段，确保旧配置也能拿到新增的 show_main 等嵌套键。
            _deep_fill_defaults(cfg, DEFAULT_CONFIG)
            # 始终覆盖内置分辨率预设，确保升级后预设可用
            cfg["resolution_presets"] = {
                **build_builtin_resolution_presets(),
                **(cfg.get("resolution_presets") or {}),
            }
            # app_version 属于程序元数据，启动时统一刷新到当前内置版本。
            cfg["app_version"] = DEFAULT_CONFIG["app_version"]
            _migrate_hotkeys(cfg)
            # 迁移：v1.2.3 首发时把 OCR 别名方向写反了，自动纠正
            aliases = cfg.get("ocr_name_aliases")
            if isinstance(aliases, dict) and aliases.get("噬光嗡嗡") == "曙光瑜瑜":
                aliases.pop("噬光嗡嗡", None)
                aliases.setdefault("曙光瑜瑜", "噬光嗡嗡")
            after = json.dumps(cfg, ensure_ascii=False, sort_keys=True)
            if after != before:
                save_config(cfg)
            return cfg
        except Exception:
            pass
    cfg = _clone_default(DEFAULT_CONFIG)
    try:
        CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
    return cfg


def save_config(cfg: Dict[str, Any]) -> None:
    try:
        CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
