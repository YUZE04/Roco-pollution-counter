import cv2
import csv
import json
import time
import threading
import re
import numpy as np
import mss
import keyboard
from pathlib import Path
import tkinter as tk
from tkinter import messagebox

SAVE_FILE = Path("pollution_count.json")
CONFIG_FILE = Path("pollution_config.json")
RECORD_DIR = Path("records")
RECORD_JSONL = RECORD_DIR / "shiny_records.jsonl"
RECORD_CSV = RECORD_DIR / "shiny_records.csv"

DEFAULT_CONFIG = {
    "middle_region": {"left": 1068, "top": 200, "width": 74, "height": 43},
    "header_region": {"left": 2132, "top": 34, "width": 383, "height": 140},
    "name_in_header": {"left": 96, "top": 14, "width": 150, "height": 52},
    "base_resolution": "2560x1440",
    "active_resolution": "2560x1440",
    "base_regions": {
        "middle_region": {"left": 1068, "top": 200, "width": 74, "height": 43},
        "header_region": {"left": 2132, "top": 34, "width": 383, "height": 140},
        "name_in_header": {"left": 96, "top": 14, "width": 150, "height": 52}
    },
    "cooldown_seconds": 2.0,
    "scan_interval": 0.7,
    "confirm_frames": 1,
    "window": {"x": 60, "y": 60, "width": 560, "height": 500},
    "compact_window": {"width": 300, "height": 400},
    "hotkeys": {"add": "f8", "sub": "f9", "start": "f6", "pause": "f7"},
    "unknown_species_name": "未识别",
    "always_on_top": True,
    "window_alpha": 1.0,
    "easyocr_languages": ["ch_sim", "en"],
    "easyocr_model_dir": "easyocr_models",
    "middle_keyword": "力量",
    "middle_fallback_keywords": ["力量"],
}


def today_str():
    return time.strftime("%Y-%m-%d")


def aggregate_species_totals(daily_species, fallback_species=None):
    totals = {}
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


def parse_daily_totals_text(text: str):
    result = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^(\d{4}-\d{2}-\d{2})\s*[:：]\s*(\d+)$", line)
        if m:
            result[m.group(1)] = int(m.group(2))
    return result


def parse_daily_species_text(text: str):
    result = {}
    current_date = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m_date1 = re.match(r"^\[(\d{4}-\d{2}-\d{2})\]$", line)
        m_date2 = re.match(r"^日期\s*[:：]\s*(\d{4}-\d{2}-\d{2})$", line)
        if m_date1 or m_date2:
            current_date = (m_date1 or m_date2).group(1)
            result.setdefault(current_date, {})
            continue
        if current_date is None:
            continue
        m_item = re.match(r"^(.+?)\s*[:：]\s*(\d+)$", line)
        if m_item:
            name = clean_pet_name(m_item.group(1))
            count = int(m_item.group(2))
            if name:
                result.setdefault(current_date, {})[name] = count
    return result


def normalize_text(text: str) -> str:
    text = re.sub(r"\s+", "", str(text))
    text = text.replace("，", ",").replace("。", ".")
    text = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff,.\-♂♀级]", "", text)
    return text.strip()


def clean_pet_name(text: str) -> str:
    text = normalize_text(text)
    text = text.replace("♂", "").replace("♀", "")
    text = re.sub(r"级$", "", text)
    text = re.sub(r"[0-9]+$", "", text)
    text = re.sub(r"^[^一-鿿A-Za-z]+", "", text)
    text = re.sub(r"[^一-鿿A-Za-z]+$", "", text)
    text = text.strip("-.，,。 ")
    return text or "未识别"


def pet_name_candidate_score(text: str, conf: float = 0.0) -> float:
    t = clean_pet_name(text)
    if not t or t == "未识别":
        return -999.0
    score = float(conf) * 10.0
    chinese_len = len(re.findall(r"[一-鿿]", t))
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


def contains_keyword_fuzzy(text, keyword):
    t = normalize_text(text)
    k = normalize_text(keyword)
    if not t or not k:
        return False
    if k in t:
        return True
    matched = sum(1 for ch in k if ch in t)
    return matched / max(len(k), 1) >= 0.7


class LocalEasyOCRReader:
    def __init__(self, config_getter):
        self.config_getter = config_getter
        self.reader = None
        self.error = ""
        self.ready = False
        self.loading = False

    def ensure_loaded(self):
        if self.ready or self.loading:
            return self.ready
        self.loading = True
        try:
            import easyocr
            cfg = self.config_getter()
            model_dir = Path(cfg.get("easyocr_model_dir", "easyocr_models"))
            model_dir.mkdir(exist_ok=True)
            self.reader = easyocr.Reader(
                cfg.get("easyocr_languages", ["ch_sim", "en"]),
                gpu=False,
                model_storage_directory=str(model_dir),
                download_enabled=False,
                verbose=False,
            )
            self.ready = True
            self.error = ""
        except Exception as e:
            self.ready = False
            self.error = str(e)
        finally:
            self.loading = False
        return self.ready

    def easyocr_region(self, image, region, scale=2, preprocess_mode="gray"):
        if not self.ensure_loaded():
            return [], self.error or "EasyOCR 未就绪"

        x, y, w, h = region["left"], region["top"], region["width"], region["height"]
        crop = image[y:y + h, x:x + w]
        if crop is None or crop.size == 0:
            return [], "区域截图为空"

        crop_big = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        processed = crop_big
        if preprocess_mode == "gray":
            processed = cv2.cvtColor(crop_big, cv2.COLOR_BGR2GRAY)
        elif preprocess_mode == "binary":
            gray = cv2.cvtColor(crop_big, cv2.COLOR_BGR2GRAY)
            _, processed = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        elif preprocess_mode == "binary_inv":
            gray = cv2.cvtColor(crop_big, cv2.COLOR_BGR2GRAY)
            _, processed = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        elif preprocess_mode == "clahe":
            gray = cv2.cvtColor(crop_big, cv2.COLOR_BGR2GRAY)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            processed = clahe.apply(gray)

        try:
            ocr_results = self.reader.readtext(processed, detail=1)
        except Exception as e:
            return [], str(e)

        parsed = []
        for item in ocr_results:
            if len(item) < 3:
                continue
            box, text, conf = item
            xs = [int(p[0] / scale) for p in box]
            ys = [int(p[1] / scale) for p in box]
            left = min(xs) + x
            top = min(ys) + y
            right = max(xs) + x
            bottom = max(ys) + y
            parsed.append({
                "text": str(text),
                "confidence": float(conf),
                "middle": {"left": left, "top": top, "width": right - left, "height": bottom - top},
                "center": {"x": left + (right - left) // 2, "y": top + (bottom - top) // 2},
            })
        return parsed, ""

    def get_absolute_name_region(self):
        cfg = self.config_getter()
        header = cfg["header_region"]
        rel = cfg["name_in_header"]
        return {
            "left": header["left"] + rel["left"],
            "top": header["top"] + rel["top"],
            "width": rel["width"],
            "height": rel["height"],
        }

    def read_middle_trigger(self, screen_bgr):
        cfg = self.config_getter()
        results, err = self.easyocr_region(
            image=screen_bgr,
            region=cfg["middle_region"],
            scale=2,
            preprocess_mode="gray",
        )
        if err:
            return False, "", 0.0, err

        matched = [item for item in results if contains_keyword_fuzzy(item["text"], cfg["middle_keyword"])]
        if not matched:
            fallback_keywords = cfg.get("middle_fallback_keywords", [])
            for item in results:
                t = normalize_text(item["text"])
                if any(k in t for k in fallback_keywords):
                    matched.append(item)

        if matched:
            best = sorted(matched, key=lambda x: x["confidence"], reverse=True)[0]
            return True, normalize_text(best["text"]), float(best["confidence"]), ""

        if results:
            best = sorted(results, key=lambda x: x["confidence"], reverse=True)[0]
            return False, normalize_text(best["text"]), float(best["confidence"]), ""

        return False, "", 0.0, ""

    def read_header_name(self, screen_bgr):
        abs_region = self.get_absolute_name_region()
        all_results = []
        err_msgs = []
        for scale, mode in [(4, "binary"), (5, "binary"), (4, "binary_inv"), (4, "clahe"), (3, "gray")]:
            results, err = self.easyocr_region(
                image=screen_bgr,
                region=abs_region,
                scale=scale,
                preprocess_mode=mode,
            )
            if err:
                err_msgs.append(err)
            for item in results:
                cleaned = clean_pet_name(item.get("text", ""))
                if cleaned and cleaned != "未识别":
                    all_results.append({
                        "raw": item.get("text", ""),
                        "clean": cleaned,
                        "confidence": float(item.get("confidence", 0.0)),
                        "score": pet_name_candidate_score(item.get("text", ""), float(item.get("confidence", 0.0))),
                    })

        if not all_results:
            return "", 0.0, err_msgs[0] if err_msgs else ""

        merged = {}
        for item in all_results:
            key = item["clean"]
            if key not in merged:
                merged[key] = {"count": 0, "best_conf": 0.0, "best_score": -999.0}
            merged[key]["count"] += 1
            merged[key]["best_conf"] = max(merged[key]["best_conf"], item["confidence"])
            merged[key]["best_score"] = max(merged[key]["best_score"], item["score"])

        ranked = sorted(
            merged.items(),
            key=lambda kv: (kv[1]["count"], kv[1]["best_score"], kv[1]["best_conf"], len(kv[0])),
            reverse=True,
        )
        best_name, meta = ranked[0]
        return best_name, float(meta["best_conf"]), ""


class App:
    def __init__(self):
        self.config_data = self.load_config()
        self.data = self.load_data()
        self.total_count = int(self.data.get("count", 0))
        self.species_counts = dict(self.data.get("species_counts", {}))
        self.daily_totals = dict(self.data.get("daily_totals", {}))
        self.daily_species = dict(self.data.get("daily_species", {}))
        self.species_total_counts = dict(self.data.get("species_total_counts", aggregate_species_totals(self.daily_species, self.species_counts)))
        if today_str() not in self.daily_totals and int(self.total_count) > 0:
            self.daily_totals[today_str()] = int(self.total_count)
        if today_str() not in self.daily_species and self.species_counts:
            self.daily_species[today_str()] = dict(self.species_counts)
        self.session_count = 0
        self.last_species_name = "无"
        self.running = False
        self.paused = False
        self.worker = None
        self.last_detect_time = 0.0
        self.confirm_hit_streak = 0
        self.hotkey_handles = []
        self._ui_switching = False
        self._last_toggle_monitor_time = 0.0
        self._hotkey_debounce_seconds = 0.45
        self.awaiting_hotkey = None
        self._poll_key_state = {}
        self._polling_hotkeys_started = False
        self._hotkey_poll_thread = None
        self._hotkey_last_fire = {}
        self._hotkey_debounce_seconds = 0.45
        self._last_status_push_time = 0.0
        self._last_status_push_text = None
        self.ocr = LocalEasyOCRReader(lambda: self.config_data)
        self.middle_template = None
        self.middle_template_path = str(self.config_data.get("middle_template_path", "template_middle.png"))
        self.middle_template_threshold = float(self.config_data.get("middle_template_threshold", 0.58))
        self.load_middle_template()
        self.compact_species_text = None
        self.in_compact_mode = False

        self.root = tk.Tk()
        self.root.title("污染计数器")
        win = self.config_data["window"]
        self.normal_size = (int(win["width"]), int(win["height"]))
        compact = self.config_data["compact_window"]
        self.compact_size = (max(300, int(compact["width"])), max(320, int(compact["height"])))
        self.root.geometry(f"{self.normal_size[0]}x{self.normal_size[1]}+{win['x']}+{win['y']}")
        self.root.configure(bg="#1a1023")
        self.root.resizable(True, True)
        self.root.bind("<Configure>", self.on_root_configure)
        self.root.attributes("-topmost", bool(self.config_data.get("always_on_top", True)))
        self.root.attributes("-alpha", max(0.30, min(1.00, float(self.config_data.get("window_alpha", 1.0)))))

        self.count_var = tk.StringVar()
        self.session_var = tk.StringVar()
        self.status_var = tk.StringVar(value="未启动")
        self.species_var = tk.StringVar(value="当前精灵: 无")
        self.pause_tip_var = tk.StringVar(value="")
        self.runtime_state_var = tk.StringVar(value="未启动")
        self.compact_hint_var = tk.StringVar(value="提示: F6启停  F7暂停  F8加  F9减")
        self.tip_var = tk.StringVar()
        self.ocr_state_var = tk.StringVar(value="EasyOCR状态: 未检查")

        hk = self.config_data["hotkeys"]
        self.add_key_var = tk.StringVar(value=hk.get("add", "f8"))
        self.sub_key_var = tk.StringVar(value=hk.get("sub", "f9"))
        self.start_key_var = tk.StringVar(value=hk.get("start", "f6"))
        self.pause_key_var = tk.StringVar(value=hk.get("pause", "f7"))
        self.top_var = tk.BooleanVar(value=bool(self.config_data.get("always_on_top", True)))
        self.alpha_var = tk.DoubleVar(value=float(self.config_data.get("window_alpha", 1.0)))
        self.model_dir_var = tk.StringVar(value=self.config_data.get("easyocr_model_dir", "easyocr_models"))
        self.resolution_var = tk.StringVar(value=str(self.config_data.get("active_resolution", "2560x1440")))

        self._alpha_job = None
        self._last_applied_alpha = None
        self._last_bg_alpha = None

        self.apply_resolution_preset(self.resolution_var.get(), show_message=False)

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.sync_memory_from_today()
        self.build_settings_ui()
        self.register_hotkeys()
        self.update_display()
        self.root.after(500, self.update_ocr_state)
        self.start_hotkey_polling()

    def load_config(self):
        if CONFIG_FILE.exists():
            try:
                raw = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
                cfg = DEFAULT_CONFIG.copy()
                for k, v in raw.items():
                    if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                        cfg[k] = {**cfg[k], **v}
                    else:
                        cfg[k] = v
                cfg.setdefault("base_resolution", "2560x1440")
                cfg.setdefault("active_resolution", "2560x1440")
                cfg.setdefault("base_regions", {
                    "middle_region": dict(DEFAULT_CONFIG["middle_region"]),
                    "header_region": dict(DEFAULT_CONFIG["header_region"]),
                    "name_in_header": dict(DEFAULT_CONFIG["name_in_header"]),
                })
                cfg["name_in_header"]["width"] = max(140, int(cfg["name_in_header"].get("width", 140)))
                cfg["name_in_header"]["height"] = max(48, int(cfg["name_in_header"].get("height", 48)))
                cfg["name_in_header"]["left"] = min(int(cfg["name_in_header"].get("left", 96)), 106)
                cfg["name_in_header"]["top"] = min(int(cfg["name_in_header"].get("top", 14)), 20)
                return cfg
            except Exception:
                pass
        CONFIG_FILE.write_text(json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2), encoding="utf-8")
        return DEFAULT_CONFIG.copy()

    def save_config(self):
        try:
            self.config_data["window"]["x"] = self.root.winfo_x()
            self.config_data["window"]["y"] = self.root.winfo_y()
            self.config_data["window"]["width"] = self.normal_size[0]
            self.config_data["window"]["height"] = self.normal_size[1]
            self.config_data["compact_window"]["width"] = self.compact_size[0]
            self.config_data["compact_window"]["height"] = self.compact_size[1]
            self.config_data["always_on_top"] = bool(self.top_var.get())
            self.config_data["window_alpha"] = float(self.alpha_var.get())
            self.config_data["easyocr_model_dir"] = self.model_dir_var.get().strip() or "easyocr_models"
            self.config_data["active_resolution"] = str(self.resolution_var.get()).strip() or "2560x1440"
            CONFIG_FILE.write_text(json.dumps(self.config_data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def load_data(self):
        if SAVE_FILE.exists():
            try:
                d = json.loads(SAVE_FILE.read_text(encoding="utf-8"))
                d.setdefault("count", 0)
                d.setdefault("species_counts", {})
                d.setdefault("daily_totals", {})
                d.setdefault("daily_species", {})
                d.setdefault("species_total_counts", aggregate_species_totals(d.get("daily_species", {}), d.get("species_counts", {})))
                return d
            except Exception:
                pass
        return {"count": 0, "species_counts": {}, "daily_totals": {}, "daily_species": {}, "species_total_counts": {}}

    def save_data(self):
        SAVE_FILE.write_text(json.dumps({
            "count": self.total_count,
            "species_counts": self.species_counts,
            "daily_totals": self.daily_totals,
            "daily_species": self.daily_species,
            "species_total_counts": self.species_total_counts,
        }, ensure_ascii=False, indent=2), encoding="utf-8")

    def ensure_today_bucket(self):
        day = today_str()
        self.daily_totals.setdefault(day, int(self.total_count))
        self.daily_species.setdefault(day, dict(self.species_counts))

    def sync_today_from_memory(self):
        day = today_str()
        self.daily_totals[day] = int(self.total_count)
        self.daily_species[day] = dict(self.species_counts)

    def sync_memory_from_today(self):
        day = today_str()
        if day in self.daily_totals:
            self.total_count = int(self.daily_totals.get(day, 0))
        if day in self.daily_species:
            self.species_counts = dict(self.daily_species.get(day, {}))

    def set_compact_hint(self, text):
        self.compact_hint_var.set(text)

    def clear_root(self):
        self.compact_species_text = None
        self.in_compact_mode = False
        for w in self.root.winfo_children():
            w.destroy()

    def set_window_size(self, width, height):
        x = self.root.winfo_x()
        y = self.root.winfo_y()
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        self.root.update_idletasks()

    def parse_resolution_text(self, text):
        try:
            parts = str(text).lower().replace(" ", "").split("x")
            if len(parts) != 2:
                raise ValueError
            return max(1, int(parts[0])), max(1, int(parts[1]))
        except Exception:
            return 2560, 1440

    def scale_region_from_base(self, region, scale_x, scale_y):
        return {
            "left": int(round(float(region.get("left", 0)) * scale_x)),
            "top": int(round(float(region.get("top", 0)) * scale_y)),
            "width": max(1, int(round(float(region.get("width", 1)) * scale_x))),
            "height": max(1, int(round(float(region.get("height", 1)) * scale_y))),
        }

    def apply_resolution_preset(self, preset=None, show_message=True):
        preset = str(preset or self.resolution_var.get()).strip() or "2560x1440"
        self.resolution_var.set(preset)
        base_w, base_h = self.parse_resolution_text(self.config_data.get("base_resolution", "2560x1440"))
        target_w, target_h = self.parse_resolution_text(preset)
        scale_x = target_w / max(base_w, 1)
        scale_y = target_h / max(base_h, 1)

        base_regions = self.config_data.get("base_regions", {})
        for key in ("middle_region", "header_region", "name_in_header"):
            region = base_regions.get(key, DEFAULT_CONFIG[key])
            self.config_data[key] = self.scale_region_from_base(region, scale_x, scale_y)

        self.config_data["active_resolution"] = preset
        self.save_config()
        if show_message:
            messagebox.showinfo("分辨率切换", f"已切换到 {preset}（按比例缩放）")

    def on_root_configure(self, _event=None):
        try:
            if self.in_compact_mode:
                w = max(260, int(self.root.winfo_width()))
                h = max(260, int(self.root.winfo_height()))
                self.compact_size = (w, h)
                self.config_data["compact_window"]["width"] = w
                self.config_data["compact_window"]["height"] = h
            else:
                w = max(560, int(self.root.winfo_width()))
                h = max(500, int(self.root.winfo_height()))
                self.normal_size = (w, h)
                self.config_data["window"]["width"] = w
                self.config_data["window"]["height"] = h
                self.config_data["window"]["x"] = int(self.root.winfo_x())
                self.config_data["window"]["y"] = int(self.root.winfo_y())
        except Exception:
            pass

    def build_settings_ui(self):
        self.clear_root()
        self.root.title("污染计数器 - 设置")
        self.root.resizable(True, True)
        self.root.minsize(560, 500)
        self.set_window_size(*self.normal_size)
        frame = tk.Frame(self.root, bg="#1a1023")
        frame.pack(fill="both", expand=True, padx=10, pady=10)

        tk.Label(frame, text="今日总污染数", font=("Microsoft YaHei", 14, "bold"), fg="white", bg="#1a1023").pack(pady=(0, 6))
        tk.Label(frame, textvariable=self.count_var, font=("Microsoft YaHei", 28, "bold"), fg="#ffd66b", bg="#1a1023").pack()
        tk.Label(frame, textvariable=self.session_var, font=("Microsoft YaHei", 10), fg="#d7c5ff", bg="#1a1023").pack(pady=(4, 0))
        tk.Label(frame, textvariable=self.status_var, font=("Microsoft YaHei", 10), fg="#d7c5ff", bg="#1a1023").pack(pady=(4, 0))
        tk.Label(frame, textvariable=self.species_var, font=("Microsoft YaHei", 10), fg="#a8ffde", bg="#1a1023").pack(pady=(4, 0))

        row1 = tk.Frame(frame, bg="#1a1023")
        row1.pack(pady=4)
        tk.Button(row1, text="启动/关闭", width=10, command=self.toggle_monitor).pack(side="left", padx=4)
        tk.Button(row1, text="详情", width=8, command=self.show_species_stats).pack(side="left", padx=4)
        tk.Button(row1, text="暂停/继续", width=10, command=self.toggle_pause).pack(side="left", padx=4)

        row3 = tk.Frame(frame, bg="#1a1023")
        row3.pack(pady=8)
        tk.Label(row3, text="+污染", fg="white", bg="#1a1023").pack(side="left", padx=(0, 4))
        tk.Entry(row3, textvariable=self.add_key_var, width=8, justify="center").pack(side="left")
        tk.Button(row3, text="录制", width=6, command=lambda: self.record_hotkey("add")).pack(side="left", padx=4)
        tk.Label(row3, text="-污染", fg="white", bg="#1a1023").pack(side="left", padx=(12, 4))
        tk.Entry(row3, textvariable=self.sub_key_var, width=8, justify="center").pack(side="left")
        tk.Button(row3, text="录制", width=6, command=lambda: self.record_hotkey("sub")).pack(side="left", padx=4)
        tk.Label(row3, text="启/关", fg="white", bg="#1a1023").pack(side="left", padx=(12, 4))
        tk.Entry(row3, textvariable=self.start_key_var, width=8, justify="center").pack(side="left")
        tk.Button(row3, text="录制", width=6, command=lambda: self.record_hotkey("start")).pack(side="left", padx=4)

        row4 = tk.Frame(frame, bg="#1a1023")
        row4.pack(pady=4)
        tk.Label(row4, text="暂停", fg="white", bg="#1a1023").pack(side="left", padx=(0, 4))
        tk.Entry(row4, textvariable=self.pause_key_var, width=8, justify="center").pack(side="left")
        tk.Button(row4, text="录制", width=6, command=lambda: self.record_hotkey("pause")).pack(side="left", padx=4)
        tk.Button(row4, text="应用热键", width=9, command=self.apply_hotkey_changes).pack(side="left", padx=16)

        row5 = tk.Frame(frame, bg="#1a1023")
        row5.pack(pady=6)
        tk.Checkbutton(
            row5, text="始终置顶", variable=self.top_var, command=self.apply_topmost,
            fg="white", bg="#1a1023", selectcolor="#1a1023", activebackground="#1a1023", activeforeground="white"
        ).pack(side="left", padx=4)
        tk.Label(row5, text="透明度", fg="white", bg="#1a1023").pack(side="left", padx=(8, 4))
        tk.Scale(
            row5, from_=0.0, to=1.0, resolution=0.01, orient="horizontal", length=110,
            variable=self.alpha_var, command=self.apply_alpha, fg="white", bg="#1a1023",
            highlightthickness=0, troughcolor="#3a2d4a", activebackground="#1a1023"
        ).pack(side="left", padx=4)

        row6 = tk.Frame(frame, bg="#1a1023")
        row6.pack(pady=(2, 4))
        tk.Label(row6, text="分辨率", fg="white", bg="#1a1023").pack(side="left", padx=(0, 6))
        tk.OptionMenu(row6, self.resolution_var, "1920x1080", "2560x1440", "2560x1660").pack(side="left")
        tk.Button(row6, text="应用分辨率", width=10, command=self.on_apply_resolution).pack(side="left", padx=8)

        self.refresh_hotkey_tip()
        bottom_box = tk.Frame(frame, bg="#1a1023")
        bottom_box.pack(side="bottom", fill="x", pady=(8, 0))

        tk.Label(
            bottom_box,
            textvariable=self.tip_var,
            fg="#bfa7ee",
            bg="#1a1023",
            font=("Microsoft YaHei", 9)
        ).pack()

        tk.Label(
            bottom_box,
            text="原创作者：小丑鱼   抖音号：conflicto834",
            fg="#9f8cc9",
            bg="#1a1023",
            font=("Microsoft YaHei", 9)
        ).pack(pady=(3, 0))

        tk.Label(
            bottom_box,
            text="GitHub：https://github.com/YUZE04/-Roco-Kingdom-World-pollution-counter/tree/main",
            fg="#8ab4ff",
            bg="#1a1023",
            font=("Microsoft YaHei", 8),
            wraplength=max(320, self.normal_size[0] - 60),
            justify="center"
        ).pack(pady=(2, 0))

        self.apply_background_opacity(float(self.alpha_var.get()))

    def build_compact_ui(self):
        self.clear_root()
        self.in_compact_mode = True
        self.root.title("污染计数器")
        self.root.resizable(True, True)
        self.root.minsize(260, 260)
        self.set_window_size(*self.compact_size)
        outer = tk.Frame(self.root, bg="#1a1023")
        outer.pack(fill="both", expand=True, padx=10, pady=10)
        outer.grid_rowconfigure(5, weight=1)
        outer.grid_columnconfigure(0, weight=1)

        hk = self.config_data["hotkeys"]

        top_area = tk.Frame(outer, bg="#1a1023")
        top_area.grid(row=0, column=0, sticky="nw")

        left_area = tk.Frame(top_area, bg="#1a1023")
        left_area.pack(side="left", anchor="n", padx=(0, 8))
        tk.Label(left_area, text="今日总污染数", font=("Microsoft YaHei", 12, "bold"), fg="white", bg="#1a1023").pack(anchor="w")
        tk.Label(left_area, textvariable=self.count_var, font=("Microsoft YaHei", 30, "bold"), fg="#ffd66b", bg="#1a1023").pack(anchor="w", pady=(4, 0))

        right_area = tk.Frame(top_area, bg="#1a1023")
        right_area.pack(side="left", anchor="n", padx=(0, 0), pady=(2, 0))
        tk.Label(right_area, text=f"启/关:{hk['start']}   暂停:{hk['pause']}", font=("Microsoft YaHei", 10), fg="#d7c5ff", bg="#1a1023").pack(anchor="w", pady=(4, 2))
        tk.Label(right_area, text=f"+污:{hk['add']}   -污:{hk['sub']}", font=("Microsoft YaHei", 10), fg="#d7c5ff", bg="#1a1023").pack(anchor="w")

        tk.Label(outer, textvariable=self.session_var, font=("Microsoft YaHei", 11), fg="#f0e7ff", bg="#1a1023").grid(row=1, column=0, sticky="w", pady=(4, 0))
        tk.Label(outer, textvariable=self.species_var, font=("Microsoft YaHei", 11), fg="#a8ffde", bg="#1a1023").grid(row=2, column=0, sticky="w", pady=(2, 0))
        tk.Label(outer, textvariable=self.compact_hint_var, font=("Microsoft YaHei", 10), fg="#ffd66b", bg="#1a1023").grid(row=3, column=0, sticky="w", pady=(1, 2))

        tk.Label(outer, text="精灵统计总表", fg="white", bg="#1a1023", font=("Microsoft YaHei", 11, "bold")).grid(row=4, column=0, sticky="nw", pady=(4, 3))

        list_outer = tk.Frame(outer, bg="#1a1023")
        list_outer.grid(row=5, column=0, sticky="nsew")
        list_outer.grid_rowconfigure(0, weight=1)
        list_outer.grid_columnconfigure(0, weight=1)

        self.compact_species_text = tk.Listbox(
            list_outer,
            font=("Consolas", 10),
            bg="#241537",
            fg="#d7f7ff",
            relief="flat",
            bd=0,
            highlightthickness=0,
            activestyle="none",
            selectbackground="#33204a",
            selectforeground="#d7f7ff",
            exportselection=False,
        )
        self.compact_species_text.grid(row=0, column=0, sticky="nsew")
        self.compact_species_scrollbar = tk.Scrollbar(list_outer, orient="vertical", command=self.compact_species_text.yview)
        self.compact_species_scrollbar.grid(row=0, column=1, sticky="ns")
        self.compact_species_text.config(yscrollcommand=self.compact_species_scrollbar.set)
        self.apply_background_opacity(float(self.alpha_var.get()))

    def enter_compact_mode(self):
        self._ui_switching = True
        self.build_compact_ui()
        self.update_display()
        self.root.update_idletasks()
        self.apply_background_opacity(float(self.alpha_var.get()))
        self.root.after(260, lambda: setattr(self, "_ui_switching", False))

    def apply_compact_alpha(self):
        if not self.running or not self.in_compact_mode:
            return
        self.apply_background_opacity(float(self.alpha_var.get()))


    def enter_settings_mode(self):
        self._ui_switching = True
        self.in_compact_mode = False
        self.build_settings_ui()
        self.set_window_size(*self.normal_size)
        self.update_display()
        self.apply_background_opacity(float(self.alpha_var.get()))
        try:
            self.root.deiconify()
            self.root.lift()
            self.root.update()
            self.root.update_idletasks()
        except Exception:
            pass
        self.root.after(260, lambda: setattr(self, "_ui_switching", False))

    def _blend_hex(self, color1, color2, t):
        t = max(0.0, min(1.0, float(t)))
        c1 = color1.lstrip("#")
        c2 = color2.lstrip("#")
        r1, g1, b1 = int(c1[0:2], 16), int(c1[2:4], 16), int(c1[4:6], 16)
        r2, g2, b2 = int(c2[0:2], 16), int(c2[2:4], 16), int(c2[4:6], 16)
        r = round(r1 + (r2 - r1) * t)
        g = round(g1 + (g2 - g1) * t)
        b = round(b1 + (b2 - b1) * t)
        return f"#{r:02x}{g:02x}{b:02x}"

    def _clamp_alpha(self, value):
        try:
            value = float(value)
        except Exception:
            value = 1.0
        return max(0.30, min(1.00, value))

    def _apply_real_alpha(self, value=None):
        value = self._clamp_alpha(self.alpha_var.get() if value is None else value)
        real_alpha = value
        if self._last_applied_alpha is not None and abs(self._last_applied_alpha - real_alpha) < 0.005:
            return
        self._last_applied_alpha = real_alpha
        try:
            self.root.attributes("-alpha", real_alpha)
            try:
                self.root.wm_attributes("-alpha", real_alpha)
            except Exception:
                pass
            self.root.update_idletasks()
        except Exception:
            pass

    def _debounced_save_config(self, delay=180):
        if self._alpha_job is not None:
            try:
                self.root.after_cancel(self._alpha_job)
            except Exception:
                pass
        self._alpha_job = self.root.after(delay, self._save_alpha_config_only)

    def _save_alpha_config_only(self):
        self._alpha_job = None
        self.config_data["window_alpha"] = float(self.alpha_var.get())
        self.save_config()

    def apply_background_opacity(self, value=None):
        value = self._clamp_alpha(self.alpha_var.get() if value is None else value)
        self.config_data["window_alpha"] = value

        if self._last_bg_alpha is not None and abs(self._last_bg_alpha - value) < 0.005:
            self._apply_real_alpha(value)
            return
        self._last_bg_alpha = value

        bg_mix = 0.45 + value * 0.55
        panel_mix = 0.35 + value * 0.65
        trough_mix = 0.25 + value * 0.75

        base_bg = self._blend_hex("#000000", "#1a1023", bg_mix)
        panel_bg = self._blend_hex("#050505", "#241537", panel_mix)
        trough_bg = self._blend_hex("#101010", "#3a2d4a", trough_mix)

        try:
            self.root.configure(bg=base_bg)
        except Exception:
            pass

        def walk(widget):
            for child in widget.winfo_children():
                try:
                    klass = child.winfo_class()
                except Exception:
                    klass = ""
                try:
                    if klass in {"Frame", "LabelFrame", "Toplevel"}:
                        child.configure(bg=base_bg)
                    elif klass == "Label":
                        child.configure(bg=base_bg)
                    elif klass == "Listbox":
                        child.configure(bg=panel_bg)
                    elif klass == "Text":
                        child.configure(bg=panel_bg)
                    elif klass == "Canvas":
                        child.configure(bg=base_bg, highlightthickness=0)
                    elif klass == "Checkbutton":
                        child.configure(bg=base_bg, activebackground=base_bg, selectcolor=base_bg)
                    elif klass == "Scale":
                        child.configure(bg=base_bg, activebackground=base_bg, troughcolor=trough_bg, highlightthickness=0)
                    elif klass == "Scrollbar":
                        child.configure(bg=panel_bg, activebackground=panel_bg, troughcolor=base_bg)
                except Exception:
                    pass
                walk(child)

        walk(self.root)
        self._apply_real_alpha(value)

    def update_ocr_state(self):
        if self.ocr.ready:
            self.ocr_state_var.set("EasyOCR状态: 已就绪")
        elif self.ocr.loading:
            self.ocr_state_var.set("EasyOCR状态: 加载中")
        elif self.ocr.error:
            self.ocr_state_var.set("EasyOCR状态: " + self.ocr.error[:60])
        else:
            self.ocr_state_var.set("EasyOCR状态: 未检查")
        self.root.after(800, self.update_ocr_state)

    def apply_topmost(self):
        self.root.attributes("-topmost", bool(self.top_var.get()))
        self.save_config()

    def on_apply_resolution(self):
        self.apply_resolution_preset(self.resolution_var.get(), show_message=True)

    def apply_alpha(self, *_args):
        value = self._clamp_alpha(self.alpha_var.get())
        self.alpha_var.set(value)
        self.apply_background_opacity(value)
        self._debounced_save_config()

    def refresh_compact_species_list(self):
        if not self.compact_species_text:
            return
        lines = []
        if self.species_total_counts:
            for name, count in sorted(self.species_total_counts.items(), key=lambda x: (-int(x[1]), x[0])):
                lines.append(f"{name}: {int(count)}")
        else:
            lines.append("暂无记录")
        self.compact_species_text.delete(0, "end")
        for line in lines:
            self.compact_species_text.insert("end", line)

    def update_display(self):
        self.count_var.set(str(self.total_count))
        self.session_var.set(f"本次污染: {self.session_count}")
        self.species_var.set(f"当前精灵: {self.last_species_name}")
        self.refresh_runtime_status()
        self.refresh_compact_species_list()
        self.save_data()
        if self.in_compact_mode:
            try:
                self.root.update_idletasks()
            except Exception:
                pass

    def refresh_runtime_status(self):
        if self.running and self.paused:
            self.runtime_state_var.set("暂停")
        elif self.running:
            self.runtime_state_var.set("")
        else:
            self.runtime_state_var.set("")

    def manual_add(self):
        target_name = clean_pet_name(self.last_species_name)
        if target_name in ["", "无"]:
            self.status_var.set("没有上一只精灵，无法手动增加")
            self.set_compact_hint("提示: 没有上一只精灵，无法手动增加")
            return
        self.total_count += 1
        self.session_count += 1
        self.species_counts[target_name] = self.species_counts.get(target_name, 0) + 1
        self.species_total_counts[target_name] = self.species_total_counts.get(target_name, 0) + 1
        self.sync_today_from_memory()
        self.last_species_name = target_name
        self.status_var.set(f"手动+1: {target_name}")
        self.set_compact_hint(f"提示: 已手动增加 1 次 -> {target_name}")
        self.update_display()

    def manual_sub(self):
        target_name = clean_pet_name(self.last_species_name)
        if target_name in ["", "无"]:
            self.status_var.set("没有上一只精灵，无法手动减少")
            self.set_compact_hint("提示: 没有上一只精灵，无法手动减少")
            return
        current_species_count = self.species_counts.get(target_name, 0)
        if current_species_count <= 0 or self.total_count <= 0 or self.session_count <= 0:
            self.status_var.set(f"{target_name} 没有可减少的污染次数")
            self.set_compact_hint(f"提示: {target_name} 没有可减少的污染次数")
            return
        self.total_count -= 1
        self.session_count -= 1
        if current_species_count == 1:
            self.species_counts.pop(target_name, None)
        else:
            self.species_counts[target_name] = current_species_count - 1
        total_species_count = int(self.species_total_counts.get(target_name, 0))
        if total_species_count > 0:
            if total_species_count == 1:
                self.species_total_counts.pop(target_name, None)
            else:
                self.species_total_counts[target_name] = total_species_count - 1
        self.sync_today_from_memory()
        self.status_var.set(f"手动-1: {target_name}")
        self.set_compact_hint(f"提示: 已手动减少 1 次 -> {target_name}")
        self.update_display()

    def archive_and_clear_session(self):
        record = {
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "session_pollution_count": self.session_count,
            "last_species": self.last_species_name,
            "species_counts": dict(self.species_counts),
        }
        RECORD_DIR.mkdir(exist_ok=True)
        with open(RECORD_JSONL, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        csv_exists = RECORD_CSV.exists()
        with open(RECORD_CSV, "a", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            if not csv_exists:
                writer.writerow(["time", "session_pollution_count", "last_species", "species_counts_json"])
            writer.writerow([record["time"], record["session_pollution_count"], record["last_species"], json.dumps(record["species_counts"], ensure_ascii=False)])
        self.session_count = 0
        self.species_counts = {}
        self.last_species_name = "无"
        self.update_display()
        self.status_var.set("已存档并清空本次记录")

    def normalize_hotkey(self, value):
        return value.strip().lower().replace(" ", "")

    def refresh_hotkey_tip(self):
        hk = self.config_data["hotkeys"]
        self.tip_var.set(f'热键  启/关:{hk["start"]}  暂停:{hk["pause"]}  +污:{hk["add"]}  -污:{hk["sub"]}')

    def unregister_hotkeys(self):
        for handle in self.hotkey_handles:
            try:
                keyboard.remove_hotkey(handle)
            except Exception:
                try:
                    keyboard.unhook(handle)
                except Exception:
                    pass
        self.hotkey_handles.clear()

    def toggle_monitor(self):
        now = time.monotonic()
        if self._ui_switching:
            return
        if now - float(self._last_toggle_monitor_time) < 0.6:
            return
        self._last_toggle_monitor_time = now
        if self.running:
            self.stop_monitor()
        else:
            self.start_monitor()

    def _run_on_ui(self, func, *args, **kwargs):
        try:
            self.root.after(0, lambda: func(*args, **kwargs))
        except Exception:
            pass

    def set_status_async(self, text, min_interval=0.25, force=False):
        now = time.time()
        if (not force) and text == self._last_status_push_text and (now - self._last_status_push_time) < min_interval:
            return
        if (not force) and (now - self._last_status_push_time) < min_interval:
            return
        self._last_status_push_time = now
        self._last_status_push_text = text
        self._run_on_ui(self.status_var.set, text)

    def _trigger_hotkey_action(self, action):
        now = time.monotonic()
        last = float(self._hotkey_last_fire.get(action, 0.0))
        if now - last < float(self._hotkey_debounce_seconds):
            return
        self._hotkey_last_fire[action] = now

        if action == "add":
            self._run_on_ui(self.manual_add)
        elif action == "sub":
            self._run_on_ui(self.manual_sub)
        elif action == "start":
            self._run_on_ui(self.toggle_monitor)
        elif action == "pause":
            self._run_on_ui(self.toggle_pause)

    def start_hotkey_polling(self):
        if self._polling_hotkeys_started:
            return
        self._polling_hotkeys_started = True
        self._hotkey_poll_thread = threading.Thread(target=self.poll_hotkeys, daemon=True)
        self._hotkey_poll_thread.start()

    def poll_hotkeys(self):
        while True:
            try:
                hk = dict(self.config_data.get("hotkeys", {}))
                for action in ("add", "sub", "start", "pause"):
                    key = self.normalize_hotkey(hk.get(action, ""))
                    if not key:
                        continue
                    pressed = False
                    try:
                        pressed = bool(keyboard.is_pressed(key))
                    except Exception:
                        pressed = False

                    prev = bool(self._poll_key_state.get(action, False))
                    if pressed and not prev:
                        self._trigger_hotkey_action(action)
                    self._poll_key_state[action] = pressed
                time.sleep(0.03)
            except Exception:
                time.sleep(0.10)

    def register_hotkeys(self):
        self.unregister_hotkeys()
        hk = self.config_data["hotkeys"]
        self._poll_key_state = {}
        self._hotkey_last_fire = {}
        ok = 0
        errors = []
        try:
            self.hotkey_handles.append(keyboard.add_hotkey(hk["add"], lambda: self._trigger_hotkey_action("add"), suppress=False, trigger_on_release=True))
            ok += 1
        except Exception as e:
            errors.append(f"+污失败: {e}")
        try:
            self.hotkey_handles.append(keyboard.add_hotkey(hk["sub"], lambda: self._trigger_hotkey_action("sub"), suppress=False, trigger_on_release=True))
            ok += 1
        except Exception as e:
            errors.append(f"-污失败: {e}")
        try:
            self.hotkey_handles.append(keyboard.add_hotkey(hk["start"], lambda: self._trigger_hotkey_action("start"), suppress=False, trigger_on_release=True))
            ok += 1
        except Exception as e:
            errors.append(f"启关失败: {e}")
        try:
            self.hotkey_handles.append(keyboard.add_hotkey(hk["pause"], lambda: self._trigger_hotkey_action("pause"), suppress=False, trigger_on_release=True))
            ok += 1
        except Exception as e:
            errors.append(f"暂停失败: {e}")

        if ok == 4:
            self.status_var.set("全局热键已注册")
        elif ok > 0:
            self.status_var.set("部分热键注册成功")
        else:
            self.status_var.set("全局热键注册失败")
        if errors:
            print("[hotkey]", " | ".join(errors))
        self.refresh_hotkey_tip()

    def record_hotkey(self, mode):
        if self.awaiting_hotkey is not None:
            return
        self.awaiting_hotkey = mode
        self.status_var.set("请按下新的快捷键...")
        threading.Thread(target=self._record_hotkey_worker, daemon=True).start()

    def _record_hotkey_worker(self):
        try:
            hotkey = self.normalize_hotkey(keyboard.read_hotkey(suppress=False))
            if self.awaiting_hotkey == "add":
                self.root.after(0, lambda: self.add_key_var.set(hotkey))
            elif self.awaiting_hotkey == "sub":
                self.root.after(0, lambda: self.sub_key_var.set(hotkey))
            elif self.awaiting_hotkey == "start":
                self.root.after(0, lambda: self.start_key_var.set(hotkey))
            elif self.awaiting_hotkey == "pause":
                self.root.after(0, lambda: self.pause_key_var.set(hotkey))
            self.root.after(0, lambda: self.status_var.set(f"已录制: {hotkey}"))
        except Exception as e:
            self.root.after(0, lambda: self.status_var.set(f"录制失败: {e}"))
        finally:
            self.awaiting_hotkey = None
        self._last_status_push_time = 0.0
        self._last_status_push_text = None

    def apply_hotkey_changes(self):
        add_key = self.normalize_hotkey(self.add_key_var.get())
        sub_key = self.normalize_hotkey(self.sub_key_var.get())
        start_key = self.normalize_hotkey(self.start_key_var.get())
        pause_key = self.normalize_hotkey(self.pause_key_var.get())

        keys = [add_key, sub_key, start_key, pause_key]
        if any(not k for k in keys):
            messagebox.showerror("设置失败", "按键不能为空。")
            return
        if len(set(keys)) != len(keys):
            messagebox.showerror("设置失败", "四个按键不能重复。")
            return

        self.config_data["hotkeys"]["add"] = add_key
        self.config_data["hotkeys"]["sub"] = sub_key
        self.config_data["hotkeys"]["start"] = start_key
        self.config_data["hotkeys"]["pause"] = pause_key
        self.register_hotkeys()
        self.save_config()
        self.status_var.set("热键已更新")

    def show_species_stats(self):
        top = tk.Toplevel(self.root)
        top.title("精灵污染统计")
        top.attributes("-topmost", True)
        top.geometry("760x460")
        top.resizable(True, True)
        top.configure(bg="#171021")

        tk.Label(
            top,
            text="污染统计详情",
            font=("Microsoft YaHei", 13, "bold"),
            fg="white",
            bg="#171021"
        ).pack(pady=10)

        main = tk.Frame(top, bg="#171021")
        main.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        left_frame = tk.Frame(main, bg="#171021")
        left_frame.pack(side="left", fill="both", expand=True, padx=(0, 6))

        right_frame = tk.Frame(main, bg="#171021")
        right_frame.pack(side="left", fill="both", expand=True, padx=(6, 0))

        tk.Label(
            left_frame,
            text="每日总污染数",
            font=("Microsoft YaHei", 11, "bold"),
            fg="white",
            bg="#171021"
        ).pack(anchor="w", pady=(0, 6))

        left_text = tk.Text(
            left_frame,
            font=("Consolas", 10),
            bg="#221532",
            fg="#f3e9ff",
            insertbackground="white",
            undo=True
        )
        left_text.pack(fill="both", expand=True)

        tk.Label(
            right_frame,
            text="精灵统计总表",
            font=("Microsoft YaHei", 11, "bold"),
            fg="white",
            bg="#171021"
        ).pack(anchor="w", pady=(0, 6))

        right_text = tk.Text(
            right_frame,
            font=("Consolas", 10),
            bg="#221532",
            fg="#f3e9ff",
            insertbackground="white",
            undo=True
        )
        right_text.pack(fill="both", expand=True)

        if self.daily_totals:
            for day, count in sorted(self.daily_totals.items()):
                left_text.insert("end", f"{day}: {int(count)}\n")
        else:
            left_text.insert("end", "暂无记录\n")

        if self.species_total_counts:
            for name, count in sorted(self.species_total_counts.items(), key=lambda x: (-int(x[1]), x[0])):
                right_text.insert("end", f"{name}: {int(count)}\n")
        else:
            right_text.insert("end", "暂无记录\n")

        btn_row = tk.Frame(top, bg="#171021")
        btn_row.pack(fill="x", padx=10, pady=(0, 10))

        def save_detail_edits(show_message=False):
            try:
                new_daily = {}
                for raw_line in left_text.get("1.0", "end").splitlines():
                    line = raw_line.strip()
                    if not line or line == "暂无记录":
                        continue
                    if ":" not in line:
                        raise ValueError(f"每日总污染数格式错误: {raw_line}")
                    day, count = line.split(":", 1)
                    day = day.strip()
                    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
                        raise ValueError(f"日期格式错误: {day}")
                    value = int(count.strip())
                    if value < 0:
                        raise ValueError(f"数量不能小于 0: {raw_line}")
                    new_daily[day] = value

                new_species_total = {}
                for raw_line in right_text.get("1.0", "end").splitlines():
                    line = raw_line.strip()
                    if not line or line == "暂无记录":
                        continue
                    if ":" not in line:
                        raise ValueError(f"精灵统计格式错误: {raw_line}")
                    name, count = line.split(":", 1)
                    clean_name = clean_pet_name(name.strip())
                    if not clean_name:
                        raise ValueError(f"精灵名字不能为空: {raw_line}")
                    value = int(count.strip())
                    if value < 0:
                        raise ValueError(f"数量不能小于 0: {raw_line}")
                    new_species_total[clean_name] = value

                self.daily_totals = new_daily
                self.species_total_counts = new_species_total
                self.data["daily_totals"] = self.daily_totals
                self.data["species_total_counts"] = self.species_total_counts

                day = today_str()
                self.total_count = int(self.daily_totals.get(day, 0))
                self.sync_today_from_memory()
                self.save_data()
                self.update_display()
                self.status_var.set("详情已保存")
                self.set_compact_hint("提示: 详情内容已保存")
                if show_message:
                    messagebox.showinfo("保存成功", "详情内容已保存。")
                return True
            except Exception as e:
                if show_message:
                    messagebox.showerror("保存失败", f"格式有误：{e}")
                else:
                    self.status_var.set(f"详情自动保存失败: {e}")
                    self.set_compact_hint("提示: 详情自动保存失败")
                return False

        def on_detail_close():
            save_detail_edits(show_message=False)
            top.destroy()

        tk.Button(btn_row, text="保存", width=10, command=lambda: save_detail_edits(show_message=True)).pack(side="right")
        top.protocol("WM_DELETE_WINDOW", on_detail_close)
        left_text.focus_set()

    def count_detected_event(self, clean_name, _raw_name, middle_text):
        clean_name = clean_pet_name(clean_name)
        self.last_species_name = clean_name
        self.total_count += 1
        self.session_count += 1
        self.species_counts[clean_name] = self.species_counts.get(clean_name, 0) + 1
        self.species_total_counts[clean_name] = self.species_total_counts.get(clean_name, 0) + 1
        self.sync_today_from_memory()
        self.status_var.set(f"命中: {middle_text[:18]}")
        self.species_var.set(f"当前精灵: {clean_name}")
        self.set_compact_hint(f"提示: 本次记录 -> {clean_name}")
        self.update_display()
        try:
            self.root.update_idletasks()
        except Exception:
            pass

    def start_monitor(self):
        self.config_data["easyocr_model_dir"] = self.model_dir_var.get().strip() or "easyocr_models"
        if not self.ocr.ensure_loaded():
            messagebox.showerror("OCR未就绪", "EasyOCR 不可用。")
            return
        if self.running:
            return
        self.running = True
        self.paused = False
        self.confirm_hit_streak = 0
        self.last_detect_time = 0.0
        self.pause_tip_var.set("")
        self.refresh_runtime_status()
        self.status_var.set("监测中")
        self.set_compact_hint("")
        self.enter_compact_mode()
        self.worker = threading.Thread(target=self.detect_loop, daemon=True)
        self.worker.start()

    def toggle_pause(self):
        if not self.running:
            self.status_var.set("未启动，无法暂停")
            return
        self.paused = not self.paused
        self.pause_tip_var.set("")
        self.refresh_runtime_status()
        self.status_var.set("已暂停" if self.paused else "已继续")
        self.set_compact_hint("提示: 已暂停" if self.paused else "提示: 已继续运行")

    def stop_monitor(self):
        self.running = False
        self.paused = False
        self.pause_tip_var.set("")
        self.in_compact_mode = False
        self.refresh_runtime_status()
        self.status_var.set("已停止")
        self.set_compact_hint("提示: F6 启动，F7 暂停，F8 加，F9 减")
        self.enter_settings_mode()





    def preprocess_middle_for_match(self, bgr):
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (3, 3), 0)
        # 亮字、暗背景的场景下，优先提取亮字
        _, binary = cv2.threshold(gray, 180, 255, cv2.THRESH_BINARY)
        kernel = np.ones((2, 2), np.uint8)
        binary = cv2.dilate(binary, kernel, iterations=1)
        return binary

    def load_middle_template(self):
        try:
            tpl_path = Path(self.middle_template_path)
            if not tpl_path.exists():
                self.middle_template = None
                return False
            tpl = cv2.imread(str(tpl_path))
            if tpl is None:
                self.middle_template = None
                return False
            self.middle_template = self.preprocess_middle_for_match(tpl)
            return True
        except Exception:
            self.middle_template = None
            return False

    def match_middle_template(self, middle_bgr, threshold=None):
        if threshold is None:
            threshold = self.middle_template_threshold
        if self.middle_template is None:
            return False, 0.0

        img_bin = self.preprocess_middle_for_match(middle_bgr)
        tpl_bin = self.middle_template

        ih, iw = img_bin.shape[:2]
        th, tw = tpl_bin.shape[:2]
        if ih < th or iw < tw:
            return False, 0.0

        res = cv2.matchTemplate(img_bin, tpl_bin, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, _ = cv2.minMaxLoc(res)
        return bool(max_val >= threshold), float(max_val)




    def detect_loop(self):
        cooldown = max(0.0, float(self.config_data.get("cooldown_seconds", 2.0)))
        base_scan_interval = float(self.config_data.get("scan_interval", 0.70))
        confirm_frames = int(self.config_data.get("confirm_frames", 1))
        last_pause_status = False

        prev_middle_thumb = None
        unchanged_loops = 0
        diff_threshold = 2.0
        bright_candidate_streak = 0

        with mss.mss() as sct:
            while self.running:
                try:
                    if self.paused:
                        if not last_pause_status:
                            self.set_status_async("已暂停", force=True)
                            last_pause_status = True
                        time.sleep(max(base_scan_interval, 0.7))
                        continue

                    if last_pause_status:
                        self.set_status_async("已继续", force=True)
                        last_pause_status = False

                    cfg = self.config_data
                    middle_region = dict(cfg["middle_region"])

                    middle_frame = np.array(sct.grab(middle_region))
                    middle_bgr = cv2.cvtColor(middle_frame, cv2.COLOR_BGRA2BGR)
                    middle_gray = cv2.cvtColor(middle_frame, cv2.COLOR_BGRA2GRAY)

                    thumb = cv2.resize(
                        middle_gray, (0, 0), fx=0.25, fy=0.25, interpolation=cv2.INTER_AREA
                    )

                    run_middle_ocr = False
                    adaptive_sleep = base_scan_interval

                    if prev_middle_thumb is not None and prev_middle_thumb.shape == thumb.shape:
                        diff = cv2.absdiff(thumb, prev_middle_thumb)
                        diff_mean = float(diff.mean())
                        if diff_mean < diff_threshold:
                            unchanged_loops += 1
                            if unchanged_loops < 4:
                                adaptive_sleep = base_scan_interval
                            elif unchanged_loops < 10:
                                adaptive_sleep = max(base_scan_interval, 0.9)
                            else:
                                adaptive_sleep = max(base_scan_interval, 1.2)
                        else:
                            unchanged_loops = 0
                            adaptive_sleep = base_scan_interval
                    else:
                        unchanged_loops = 0

                    prev_middle_thumb = thumb

                    # 第一层：亮字预判，只有像素数量像是出现了亮字，才继续 OCR
                    blurred = cv2.GaussianBlur(middle_gray, (3, 3), 0)
                    _, binary = cv2.threshold(blurred, 185, 255, cv2.THRESH_BINARY)
                    white_pixels = int(cv2.countNonZero(binary))

                    # 两帧连续像有字，再 OCR，降低误触发和 CPU
                    if white_pixels >= 120:
                        bright_candidate_streak += 1
                    else:
                        bright_candidate_streak = 0

                    if bright_candidate_streak >= 2:
                        run_middle_ocr = True

                    triggered = False
                    middle_text = ""

                    if run_middle_ocr:
                        local_middle_region = {
                            "left": 0,
                            "top": 0,
                            "width": int(middle_bgr.shape[1]),
                            "height": int(middle_bgr.shape[0]),
                        }

                        all_middle_results = []
                        err_msg = ""

                        for scale, mode in [(3, "binary"), (3, "gray")]:
                            results, err = self.ocr.easyocr_region(
                                image=middle_bgr,
                                region=local_middle_region,
                                scale=scale,
                                preprocess_mode=mode,
                            )
                            if err and not err_msg:
                                err_msg = err
                            all_middle_results.extend(results)

                        keyword = normalize_text(cfg.get("middle_keyword", "力量"))
                        fallback_keywords = [normalize_text(x) for x in cfg.get("middle_fallback_keywords", ["力量"])]

                        best_text = ""
                        best_conf = 0.0
                        for item in all_middle_results:
                            t = normalize_text(item.get("text", ""))
                            if not t:
                                continue
                            if keyword and keyword in t:
                                triggered = True
                                if float(item.get("confidence", 0.0)) >= best_conf:
                                    best_text = t
                                    best_conf = float(item.get("confidence", 0.0))
                            elif any(k and k in t for k in fallback_keywords):
                                triggered = True
                                if float(item.get("confidence", 0.0)) >= best_conf:
                                    best_text = t
                                    best_conf = float(item.get("confidence", 0.0))

                        if triggered:
                            middle_text = best_text or keyword or "力量"
                            self.set_status_async(f"命中候选: {middle_text[:18]}", min_interval=0.6)
                            bright_candidate_streak = 0
                        elif err_msg:
                            self.set_status_async(f"OCR错误: {err_msg[:24]}", min_interval=1.2)

                    now = time.time()

                    if triggered:
                        self.confirm_hit_streak += 1
                    else:
                        self.confirm_hit_streak = 0

                    if triggered and self.confirm_hit_streak >= confirm_frames and (now - self.last_detect_time) >= cooldown:
                        self.last_detect_time = now
                        self.confirm_hit_streak = 0
                        time.sleep(float(self.config_data.get("name_read_delay", 0.2)))

                        clean_name = self.config_data.get("unknown_species_name", "未识别")
                        try:
                            abs_name_region = self.ocr.get_absolute_name_region()
                            name_frame = np.array(sct.grab(abs_name_region))
                            name_bgr = cv2.cvtColor(name_frame, cv2.COLOR_BGRA2BGR)
                            local_name_region = {
                                "left": 0,
                                "top": 0,
                                "width": int(name_bgr.shape[1]),
                                "height": int(name_bgr.shape[0]),
                            }

                            all_results = []
                            err_msgs = []

                            for scale, mode in [(3, "binary"), (3, "gray")]:
                                results, name_err = self.ocr.easyocr_region(
                                    image=name_bgr,
                                    region=local_name_region,
                                    scale=scale,
                                    preprocess_mode=mode,
                                )
                                if name_err:
                                    err_msgs.append(name_err)

                                for item in results:
                                    cleaned = clean_pet_name(item.get("text", ""))
                                    if cleaned and cleaned != "未识别":
                                        all_results.append({
                                            "raw": item.get("text", ""),
                                            "clean": cleaned,
                                            "confidence": float(item.get("confidence", 0.0)),
                                            "score": pet_name_candidate_score(
                                                item.get("text", ""),
                                                float(item.get("confidence", 0.0))
                                            ),
                                        })

                            if all_results:
                                merged = {}
                                for item in all_results:
                                    key = item["clean"]
                                    if key not in merged:
                                        merged[key] = {"count": 0, "best_conf": 0.0, "best_score": -999.0}
                                    merged[key]["count"] += 1
                                    merged[key]["best_conf"] = max(merged[key]["best_conf"], item["confidence"])
                                    merged[key]["best_score"] = max(merged[key]["best_score"], item["score"])

                                ranked = sorted(
                                    merged.items(),
                                    key=lambda kv: (kv[1]["count"], kv[1]["best_score"], kv[1]["best_conf"], len(kv[0])),
                                    reverse=True,
                                )
                                clean_name = clean_pet_name(ranked[0][0])
                            elif err_msgs:
                                self.set_status_async(f"名字OCR错误: {err_msgs[0][:24]}", min_interval=1.2)

                        except Exception as name_ex:
                            self.set_status_async(f"名字识别失败: {str(name_ex)[:24]}", min_interval=1.2)

                        self._run_on_ui(self.count_detected_event, clean_name, clean_name, middle_text)

                except Exception as e:
                    self.set_status_async(f"错误: {str(e)[:40]}", min_interval=1.2)

                time.sleep(adaptive_sleep)

    def on_close(self):
        self.running = False
        self.in_compact_mode = False
        self.save_data()
        self.save_config()
        self.unregister_hotkeys()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    App().run()