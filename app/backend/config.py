"""配置文件的默认值、加载与保存。"""

from __future__ import annotations

import json
from typing import Any, Dict

from .paths import CONFIG_FILE
from .utils import build_builtin_resolution_presets

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
    "app_version": "v1.2.3",
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


def load_config() -> Dict[str, Any]:
    if CONFIG_FILE.exists():
        try:
            cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            # 用默认值补齐缺失字段
            for k, v in DEFAULT_CONFIG.items():
                cfg.setdefault(k, v if not isinstance(v, (dict, list)) else json.loads(json.dumps(v)))
            # 始终覆盖内置分辨率预设，确保升级后预设可用
            cfg["resolution_presets"] = {
                **build_builtin_resolution_presets(),
                **(cfg.get("resolution_presets") or {}),
            }
            # 迁移：v1.2.3 首发时把 OCR 别名方向写反了，自动纠正
            aliases = cfg.get("ocr_name_aliases")
            if isinstance(aliases, dict) and aliases.get("噬光嗡嗡") == "曙光瑜瑜":
                aliases.pop("噬光嗡嗡", None)
                aliases.setdefault("曙光瑜瑜", "噬光嗡嗡")
            return cfg
        except Exception:
            pass
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
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
