"""无 UI、纯逻辑的工具函数。与旧版 `1.py` 中的同名函数行为完全一致。"""

from __future__ import annotations

import re
import time
from typing import Dict, Optional

_SHIGUANG_SECOND_CHAR = "光"
_RESOLUTION_ALIASES = {
    "4k": "3840x2160",
    "uhd": "3840x2160",
    "2160p": "3840x2160",
    "2k": "2560x1440",
    "qhd": "2560x1440",
    "1440p": "2560x1440",
    "fhd": "1920x1080",
    "1080p": "1920x1080",
    "720p": "1280x720",
}


def today_str() -> str:
    return time.strftime("%Y-%m-%d")


def normalize_text(text: str) -> str:
    text = re.sub(r"\s+", "", str(text))
    text = text.replace("，", ",").replace("。", ".")
    text = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff,.\-♂♀级]", "", text)
    return text.strip()


def normalize_known_pet_name(text: str) -> str:
    """把已知 OCR 易错名称归并到标准精灵名。

    噬光嗡嗡归并规则：长度为 4 且第 2 个字是「光」，一律归并。
    理由：污染频率里只有「噬光嗡嗡」这一只 X光XX 结构，
    OCR 怎么错都跑不出这个模板，直接归并最稳。
    """
    t = str(text or "").strip()
    if len(t) == 4 and t[1] == _SHIGUANG_SECOND_CHAR:
        return "噬光嗡嗡"
    return t


def clean_pet_name(text: str) -> str:
    text = normalize_text(text)
    text = text.replace("♂", "").replace("♀", "")
    text = re.sub(r"级$", "", text)
    text = re.sub(r"[0-9]+$", "", text)
    text = re.sub(r"^[^\u4e00-\u9fffA-Za-z]+", "", text)
    text = re.sub(r"[^\u4e00-\u9fffA-Za-z]+$", "", text)
    text = text.strip("-.，,。 ")
    text = normalize_known_pet_name(text)
    return text or "未识别"


def pet_name_candidate_score(text: str, conf: float = 0.0) -> float:
    t = clean_pet_name(text)
    if not t or t == "未识别":
        return -999.0
    score = float(conf) * 10.0
    chinese_len = len(re.findall(r"[\u4e00-\u9fff]", t))
    if chinese_len >= 4:
        score += 6.0
    elif chinese_len == 3:
        score += 4.0
    elif chinese_len == 2:
        score += 2.0
    elif chinese_len == 1:
        score -= 1.0
    if chinese_len > 5:
        score -= (chinese_len - 5) * 1.5
    if re.search(r"[A-Za-z0-9]", t):
        score -= 3.0
    return score


def contains_keyword_fuzzy(text: str, keyword: str) -> bool:
    t = normalize_text(text)
    k = normalize_text(keyword)
    if not t or not k:
        return False
    if k in t:
        return True
    matched = sum(1 for ch in k if ch in t)
    return matched / max(len(k), 1) >= 0.7


def aggregate_species_totals(
    daily_species: Dict[str, Dict[str, int]],
    fallback_species: Optional[Dict[str, int]] = None,
) -> Dict[str, int]:
    totals: Dict[str, int] = {}
    if isinstance(daily_species, dict):
        for _day, species_map in daily_species.items():
            if not isinstance(species_map, dict):
                continue
            for name, count in species_map.items():
                clean_name = clean_pet_name(name)
                try:
                    value = int(count)
                except Exception:
                    continue
                if not clean_name or value <= 0:
                    continue
                totals[clean_name] = totals.get(clean_name, 0) + value
    if not totals and isinstance(fallback_species, dict):
        for name, count in fallback_species.items():
            clean_name = clean_pet_name(name)
            try:
                value = int(count)
            except Exception:
                continue
            if not clean_name or value <= 0:
                continue
            totals[clean_name] = totals.get(clean_name, 0) + value
    return totals


def scale_region_pack(region_pack: dict, scale_x: float, scale_y: float) -> dict:
    return {
        key: {
            "left": int(round(float(region.get("left", 0)) * scale_x)),
            "top": int(round(float(region.get("top", 0)) * scale_y)),
            "width": max(1, int(round(float(region.get("width", 1)) * scale_x))),
            "height": max(1, int(round(float(region.get("height", 1)) * scale_y))),
        }
        for key, region in region_pack.items()
    }


def normalize_resolution_label(text: str) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""
    clean = raw.lower().replace(" ", "").replace("×", "x")
    clean = clean.split("_")[0]
    return _RESOLUTION_ALIASES.get(clean, raw)


def parse_resolution_text(text: str) -> tuple[int, int]:
    normalized = normalize_resolution_label(text)
    m = re.match(r"(\d+)\s*[x×]\s*(\d+)", str(normalized or ""))
    if m:
        return int(m.group(1)), int(m.group(2))
    return 2560, 1600


def apply_resolution_preset(
    cfg: dict,
    preset: str,
    apply_to_cfg: bool = True,
) -> str | tuple[str, dict]:
    """按分辨率应用预设区域配置。
    
    Args:
        cfg: 配置字典
        preset: 分辨率预设 (如 "2560x1600")
        apply_to_cfg: 是否直接写回 cfg，否则仅返回基础区域
        
    Returns:
        当 apply_to_cfg=True 时返回模式描述 (str)
        当 apply_to_cfg=False 时返回 (模式, 基础区域) 元组
    """
    preset = normalize_resolution_label(preset) or str(
        cfg.get("base_resolution", "2560x1600_150缩放")
    ).strip()
    presets = cfg.get("resolution_presets", {}) or {}
    base_regions = {}
    
    if preset in presets:
        pack = presets[preset]
        for key in ("middle_region", "header_region", "name_in_header"):
            if key in pack:
                base_regions[key] = dict(pack[key])
        mode = "专用预设"
    else:
        base_w, base_h = parse_resolution_text(cfg.get("base_resolution", "2560x1600"))
        tgt_w, tgt_h = parse_resolution_text(preset)
        sx = tgt_w / max(base_w, 1)
        sy = tgt_h / max(base_h, 1)
        base_regions_all = cfg.get("base_regions", {})
        for key in ("middle_region", "header_region", "name_in_header"):
            region = base_regions_all.get(key)
            if region:
                base_regions[key] = {
                    "left": int(round(region["left"] * sx)),
                    "top": int(round(region["top"] * sy)),
                    "width": max(1, int(round(region["width"] * sx))),
                    "height": max(1, int(round(region["height"] * sy))),
                }
        mode = "按比例缩放"
    
    if apply_to_cfg:
        for key in ("middle_region", "header_region", "name_in_header"):
            if key in base_regions:
                cfg[key] = dict(base_regions[key])
        cfg["active_resolution"] = preset

    return mode if apply_to_cfg else (mode, base_regions)


def build_builtin_resolution_presets() -> dict:
    reference_pack = {
        "middle_region": {"left": 1057, "top": 195, "width": 92, "height": 59},
        "header_region": {"left": 2125, "top": 30, "width": 372, "height": 150},
        "name_in_header": {"left": 99, "top": 35, "width": 204, "height": 48},
    }
    return {
        "1920x1080": scale_region_pack(reference_pack, 0.75, 0.75),
        "2560x1440": dict(reference_pack),
        "2560x1600_150缩放": dict(reference_pack),
        "1280x720": scale_region_pack(reference_pack, 0.5, 0.5),
        "1280x960": scale_region_pack(reference_pack, 0.5, 0.5),
        "3840x2160": scale_region_pack(reference_pack, 1.5, 1.5),
    }
