import cv2
import csv
import json
import os
import sys
os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
import time
import threading
import re
import numpy as np
import mss
import keyboard
from pathlib import Path
import tkinter as tk
from tkinter import messagebox
from tkinter import scrolledtext
from tkinter import font as tkfont
import webbrowser
import urllib.request
import urllib.error
import ctypes

APP_DIR = Path(__file__).resolve().parent
os.environ.setdefault("PADDLEOCR_HOME", str(APP_DIR / "paddleocr_models"))


def _enable_dpi_awareness():
    """尽早启用 DPI 感知，避免 Windows 缩放导致坐标偏移。"""
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


_enable_dpi_awareness()


def _patch_paddleocr_cpu_inference():
    """避免 PaddleOCR CPU 路径强制开启 PIR API。"""
    try:
        import paddlex.inference.utils.pp_option as pp_option
    except Exception:
        return False

    predictor_cls = getattr(pp_option, "PaddlePredictorOption", None)
    device_prop = getattr(predictor_cls, "device_type", None)
    if predictor_cls is None or getattr(predictor_cls, "_pollution_counter_cpu_patch", False):
        return False
    if not isinstance(device_prop, property) or device_prop.fset is None:
        return False

    def _device_type_setter(self, device_type):
        if device_type not in self.SUPPORT_DEVICE:
            support_run_mode_str = ", ".join(self.SUPPORT_DEVICE)
            raise ValueError(
                f"The device type must be one of {support_run_mode_str}, but received {repr(device_type)}."
            )
        self._update("device_type", device_type)
        set_env_for_device_type = getattr(pp_option, "set_env_for_device_type", None)
        if callable(set_env_for_device_type):
            set_env_for_device_type(device_type)
        os.environ["FLAGS_enable_pir_api"] = "0"

    predictor_cls.device_type = property(
        device_prop.fget,
        _device_type_setter,
        device_prop.fdel,
        device_prop.__doc__,
    )
    predictor_cls._pollution_counter_cpu_patch = True
    os.environ["FLAGS_enable_pir_api"] = "0"
    return True


def _scale_region_pack(region_pack, scale_x, scale_y):
    return {
        key: {
            "left": int(round(float(region.get("left", 0)) * scale_x)),
            "top": int(round(float(region.get("top", 0)) * scale_y)),
            "width": max(1, int(round(float(region.get("width", 1)) * scale_x))),
            "height": max(1, int(round(float(region.get("height", 1)) * scale_y))),
        }
        for key, region in region_pack.items()
    }


def _build_builtin_resolution_presets():
    reference_pack = {
        "middle_region": {"left": 1057, "top": 195, "width": 92, "height": 59},
        "header_region": {"left": 2125, "top": 30, "width": 372, "height": 150},
        "name_in_header": {"left": 99, "top": 35, "width": 204, "height": 48},
    }
    return {
        "1920x1080": _scale_region_pack(reference_pack, 0.75, 0.75),
        "2560x1440": dict(reference_pack),
        "2560x1600_150缩放": dict(reference_pack),
        "1280x720": _scale_region_pack(reference_pack, 0.5, 0.5),
        "3840x2160": _scale_region_pack(reference_pack, 1.5, 1.5),
    }


try:
    from PIL import Image, ImageDraw, ImageTk

    _PIL_UI = True
    try:
        _PIL_LANCZOS = Image.Resampling.LANCZOS
    except AttributeError:
        _PIL_LANCZOS = getattr(Image, "LANCZOS", Image.BICUBIC)
except ImportError:
    _PIL_UI = False

SAVE_FILE = Path("pollution_count.json")
CONFIG_FILE = Path("pollution_config.json")
OCR_POSITION_FILE = Path("ocr_capture_positions.json")
RECORD_DIR = Path("records")
RECORD_JSONL = RECORD_DIR / "shiny_records.jsonl"
RECORD_CSV = RECORD_DIR / "shiny_records.csv"
TODAY_ARCHIVE_JSONL = RECORD_DIR / "today_cleared_archive.jsonl"
TODAY_ARCHIVE_CSV = RECORD_DIR / "today_cleared_archive.csv"
ICON_FILE = Path(__file__).with_name("roco_counter_icon.ico")

# 全局 UI：微软雅黑 + 圆角按钮（浅灰胶囊参考常见现代控件）
UI_FONT = ("Microsoft YaHei", 10)
UI_FONT_BOLD = ("Microsoft YaHei", 10, "bold")
UI_FONT_9 = ("Microsoft YaHei", 9)
UI_FONT_8 = ("Microsoft YaHei", 8)
UI_FONT_11 = ("Microsoft YaHei", 11)
UI_FONT_TITLE = ("Microsoft YaHei", 14, "bold")
UI_FONT_COUNT = ("Microsoft YaHei", 28, "bold")
UI_FONT_COUNT_COMPACT = ("Microsoft YaHei", 30, "bold")

LOCK_ACTIVE_GREEN = "#6dffb3"
LOCK_ACTIVE_GREEN_SOFT = "#95ffd0"
LOCK_IDLE_PURPLE = "#bfa7ee"
LOCK_IDLE_LAVENDER = "#e8dcff"


def apply_dwm_rounded_corners(window):
    """Windows 11+：为 Tk 窗口启用系统圆角（失败时静默忽略）。"""
    if sys.platform != "win32" or not hasattr(ctypes, "windll"):
        return
    try:
        window.update_idletasks()
        hwnd = int(window.winfo_id())
        if hwnd <= 0:
            return
        DWMWA_WINDOW_CORNER_PREFERENCE = 33
        DWMWCP_ROUND = 2
        preference = ctypes.c_int(DWMWCP_ROUND)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            ctypes.wintypes.HWND(hwnd),
            DWMWA_WINDOW_CORNER_PREFERENCE,
            ctypes.byref(preference),
            ctypes.sizeof(preference),
        )
    except Exception:
        pass


def _measure_text_width(text, font_tuple, root):
    try:
        f = tkfont.Font(root=root, font=font_tuple)
        return int(f.measure(str(text))) + 28
    except Exception:
        return len(str(text)) * 12 + 28


def _hex_to_rgb(hex_color):
    h = str(hex_color).lstrip("#")
    if len(h) != 6:
        return (209, 213, 219)
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))


def _antialiased_round_rect_photo(w, h, radius, fill_hex, scale=3):
    """高分辨率绘制圆角矩形再缩放，边缘平滑（需 Pillow）。"""
    if not _PIL_UI or w < 2 or h < 2:
        return None
    scale = max(2, min(4, int(scale)))
    W, H = max(2, w * scale), max(2, h * scale)
    R = int(max(1, min(radius * scale, H // 2 - 1, W // 2 - 1)))
    rgb = _hex_to_rgb(fill_hex)
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)
    try:
        dr.rounded_rectangle((0, 0, W - 1, H - 1), radius=R, fill=rgb + (255,))
    except Exception:
        dr.rectangle((0, 0, W - 1, H - 1), fill=rgb + (255,))
    try:
        im = im.resize((w, h), _PIL_LANCZOS)
    except Exception:
        im = im.resize((w, h))
    return ImageTk.PhotoImage(im)


class RoundedButton(tk.Canvas):
    """圆角胶囊按钮（Canvas 绘制，风格接近浅灰圆角矩形）。"""

    def __init__(
        self,
        parent,
        text="",
        command=None,
        font=None,
        radius=12,
        fill="#d1d5db",
        fill_hover="#e8eaef",
        fill_pressed="#b8bcc6",
        fg="#1a1a2e",
        width_px=None,
        height=34,
        **kwargs,
    ):
        parent_bg = kwargs.pop("bg_parent", None)
        if parent_bg is None:
            try:
                parent_bg = parent.cget("bg")
            except Exception:
                parent_bg = "#1a1023"
        kwargs.setdefault("highlightthickness", 0)
        kwargs.setdefault("bd", 0)
        font = font or UI_FONT
        w = width_px or _measure_text_width(text, font, parent.winfo_toplevel())
        w = max(56, int(w))
        super().__init__(parent, width=w, height=height, bg=parent_bg, **kwargs)
        self._command = command
        self._text = text
        self._font = font
        self._radius = min(radius, height // 2 - 1)
        self._fill = fill
        self._fill_hover = fill_hover
        self._fill_pressed = fill_pressed
        self._fg = fg
        self._cur = fill
        self._armed = False
        self._photo = None
        self._draw(self._fill)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_down)
        self.bind("<ButtonRelease-1>", self._on_up)

    def _draw(self, fill):
        self.delete("all")
        w, h = int(self["width"]), int(self["height"])
        r = min(self._radius, h // 2 - 1, w // 2 - 1)
        x1, y1, x2, y2 = 0, 0, w - 1, h - 1
        photo = _antialiased_round_rect_photo(w, h, r, fill)
        if photo is not None:
            self._photo = photo
            self.create_image(0, 0, anchor="nw", image=self._photo)
        else:
            self._photo = None
            if r <= 1:
                self.create_rectangle(x1, y1, x2, y2, fill=fill, outline="")
            else:
                pie = {"style": tk.PIESLICE}
                self.create_rectangle(x1 + r, y1, x2 - r, y2, fill=fill, outline="")
                self.create_rectangle(x1, y1 + r, x2, y2 - r, fill=fill, outline="")
                self.create_arc(x1, y1, x1 + 2 * r, y1 + 2 * r, start=90, extent=90, fill=fill, outline="", **pie)
                self.create_arc(x2 - 2 * r, y1, x2, y1 + 2 * r, start=0, extent=90, fill=fill, outline="", **pie)
                self.create_arc(x1, y2 - 2 * r, x1 + 2 * r, y2, start=180, extent=90, fill=fill, outline="", **pie)
                self.create_arc(x2 - 2 * r, y2 - 2 * r, x2, y2, start=270, extent=90, fill=fill, outline="", **pie)
        self.create_text(w // 2, h // 2, text=self._text, fill=self._fg, font=self._font)

    def _on_enter(self, _e=None):
        if not self._armed:
            self._cur = self._fill_hover
            self._draw(self._cur)

    def _on_leave(self, _e=None):
        self._armed = False
        self._cur = self._fill
        self._draw(self._cur)

    def _on_down(self, _e=None):
        self._armed = True
        self._draw(self._fill_pressed)

    def _on_up(self, _e=None):
        was = self._armed
        self._armed = False
        self._cur = self._fill_hover
        self._draw(self._cur)
        if was and self._command:
            self._command()


def ensure_run_as_administrator():
    """Windows：非管理员时请求 UAC 提权并重启本脚本。"""
    if sys.platform != "win32":
        return True
    try:
        if ctypes.windll.shell32.IsUserAnAdmin():
            return True
    except Exception:
        return True
    try:
        script = os.path.abspath(__file__)
        params = f'"{script}"'
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 1)
    except Exception:
        try:
            ctypes.windll.user32.MessageBoxW(
                0,
                "无法请求管理员权限，请右键选择「以管理员身份运行」。",
                "需要管理员权限",
                0x10,
            )
        except Exception:
            pass
    return False


# 识别逻辑与 `roco_pollution_counter_v0.3_scan_07.py` 对齐；界面为本仓库新版 UI。
DEFAULT_CONFIG = {
    "middle_region": {"left": 1057, "top": 195, "width": 92, "height": 59},
    "header_region": {"left": 2125, "top": 30, "width": 372, "height": 150},
    "name_in_header": {"left": 99, "top": 35, "width": 204, "height": 48},
    "base_resolution": "2560x1600_150缩放",
    "active_resolution": "2560x1600_150缩放",
    "base_regions": {
        "middle_region": {"left": 1057, "top": 195, "width": 92, "height": 59},
        "header_region": {"left": 2125, "top": 30, "width": 372, "height": 150},
        "name_in_header": {"left": 99, "top": 35, "width": 204, "height": 48}
    },
    "resolution_presets": _build_builtin_resolution_presets(),
    "cooldown_seconds": 2.0,
    "scan_interval": 0.7,
    "confirm_frames": 1,
    "window": {"x": 60, "y": 60, "width": 560, "height": 620},
    "compact_window": {"width": 300, "height": 400},
    "hotkeys": {"add": "8", "sub": "9", "start": "7", "pause": "0", "lock": "-"},
    "unknown_species_name": "未识别",
    "always_on_top": True,
    "window_alpha": 1.0,
    "paddleocr_model_dir": "paddleocr_models",
    "middle_keyword": "力量",
    "middle_fallback_keywords": ["力量"],
    "header_ocr_modes": [[4, "binary"], [3, "gray"]],
    "name_read_delay": 0.0,
    "drag_bar_height": 32,
    "app_version": "v1.1.0",
    "update_info_url": "https://raw.githubusercontent.com/YUZE04/Roco-pollution-counter/main/version.json",
    "github_api_latest_url": "https://api.github.com/repos/YUZE04/Roco-pollution-counter/releases/latest",
    "release_page_url": "https://github.com/YUZE04/Roco-pollution-counter/tags",
    "game_mode_no_activate": True,
    "window_corner_placed_once": False,
    "first_startup_tip_done": False,
    "borderless_window": True,
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


def _resolve_app_path(raw_path):
    path = Path(str(raw_path).strip()).expanduser()
    if not path.is_absolute():
        path = APP_DIR / path
    return path


def _has_paddle_model_files(path, required_files):
    return path.is_dir() and all((path / filename).exists() for filename in required_files)


def _find_paddle_model_dir(root, preferred_rel_paths, required_files):
    for rel in preferred_rel_paths:
        candidate = root / rel
        if _has_paddle_model_files(candidate, required_files):
            return candidate
    if _has_paddle_model_files(root, required_files):
        return root
    if root.is_dir():
        for filename in required_files:
            for match in root.rglob(filename):
                candidate = match.parent
                if _has_paddle_model_files(candidate, required_files):
                    return candidate
    return None


class LocalPaddleOCRReader:
    """PaddleOCR 单次加载；ocr 直接接收预处理后的 ndarray。"""

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
            _patch_paddleocr_cpu_inference()
            from paddleocr import PaddleOCR
            import logging
            import warnings
            logging.getLogger("ppocr").setLevel(logging.ERROR)
            logging.getLogger("paddle").setLevel(logging.ERROR)
            cfg = self.config_getter() or {}
            model_root_value = cfg.get("paddleocr_model_dir") or "paddleocr_models"
            model_root = _resolve_app_path(model_root_value)
            det_model_dir = _find_paddle_model_dir(
                model_root / "det",
                ["PP-OCRv4_mobile_det_infer"],
                ["inference.json", "inference.pdiparams"],
            )
            rec_model_dir = _find_paddle_model_dir(
                model_root / "rec",
                ["rec"],
                ["inference.json", "inference.yml", "inference.pdiparams"],
            )
            cls_model_dir = _find_paddle_model_dir(
                model_root / "cls",
                ["cls"],
                ["inference.pdmodel", "inference.pdiparams"],
            )
            missing = []
            if det_model_dir is None:
                missing.append("det/PP-OCRv4_mobile_det_infer")
            if rec_model_dir is None:
                missing.append("rec")
            if missing:
                raise FileNotFoundError(
                    f"本地 PaddleOCR 模型不完整：{', '.join(missing)}，请确认 {model_root} 下的离线模型文件已解压。"
                )

            init_kwargs = dict(
                device="cpu",
                enable_hpi=False,
                enable_mkldnn=False,
                enable_cinn=False,
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
                text_detection_model_name="PP-OCRv4_mobile_det",
                text_detection_model_dir=str(det_model_dir),
                text_recognition_model_name="PP-OCRv3_mobile_rec",
                text_recognition_model_dir=str(rec_model_dir),
            )
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                try:
                    self.reader = PaddleOCR(**init_kwargs)
                except Exception as first_err:
                    legacy_kwargs = dict(
                        device="cpu",
                        enable_hpi=False,
                        enable_mkldnn=False,
                        enable_cinn=False,
                        use_doc_orientation_classify=False,
                        use_doc_unwarping=False,
                        use_textline_orientation=False,
                        text_detection_model_name="PP-OCRv4_mobile_det",
                        det_model_dir=str(det_model_dir),
                        text_recognition_model_name="PP-OCRv3_mobile_rec",
                        rec_model_dir=str(rec_model_dir),
                    )
                    try:
                        self.reader = PaddleOCR(**legacy_kwargs)
                    except Exception:
                        raise first_err
            self.ready = True
            self.error = ""
        except Exception as e:
            import traceback; traceback.print_exc()
            self.ready = False
            self.error = str(e)
        finally:
            self.loading = False
        return self.ready

    def easyocr_region(self, image, region, scale=2, preprocess_mode="gray"):
        if not self.ensure_loaded():
            return [], self.error or "PaddleOCR 未就绪"

        img_h, img_w = image.shape[:2]
        x = max(0, int(region["left"]))
        y = max(0, int(region["top"]))
        w = max(1, int(region["width"]))
        h = max(1, int(region["height"]))
        right = min(img_w, x + w)
        bottom = min(img_h, y + h)
        if right <= x or bottom <= y:
            return [], "区域截图为空"

        crop = image[y:bottom, x:right]
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
        # PaddleOCR 这条推理链路仍然要求 3 通道 BGR 输入。
        if processed.ndim == 2:
            processed = cv2.cvtColor(processed, cv2.COLOR_GRAY2BGR)

        try:
            result = self.reader.predict(processed)
            ocr_results = result[0] if result and result[0] is not None else []
        except Exception as e:
            return [], str(e)

        parsed = []
        if hasattr(ocr_results, "get"):
            boxes = ocr_results.get("dt_polys")
            if boxes is None or len(boxes) == 0:
                boxes = ocr_results.get("rec_boxes")
            if boxes is None:
                boxes = []
            texts = ocr_results.get("rec_texts")
            if texts is None:
                texts = []
            scores = ocr_results.get("rec_scores")
            if scores is None:
                scores = []
            for idx, box in enumerate(boxes):
                if box is None:
                    continue
                text = texts[idx] if idx < len(texts) else ""
                conf = scores[idx] if idx < len(scores) else 0.0
                pts = np.array(box, dtype=float)
                if pts.size == 0:
                    continue
                xs = [int(p[0] / scale) for p in pts]
                ys = [int(p[1] / scale) for p in pts]
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
        else:
            for item in ocr_results:
                if not item or len(item) < 2:
                    continue
                box, (text, conf) = item
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

    ocr_region = easyocr_region

    def expand_region(self, region, pad_ratio=0.0, pad_px=0, bounds=None):
        """按比例/像素向四周扩展区域，可选按屏幕边界裁剪。"""
        left = int(region.get("left", 0))
        top = int(region.get("top", 0))
        width = max(1, int(region.get("width", 1)))
        height = max(1, int(region.get("height", 1)))
        pad_x = int(round(width * float(pad_ratio))) + int(pad_px)
        pad_y = int(round(height * float(pad_ratio))) + int(pad_px)

        expanded = {
            "left": left - pad_x,
            "top": top - pad_y,
            "width": width + pad_x * 2,
            "height": height + pad_y * 2,
        }

        if bounds is None:
            return expanded

        if isinstance(bounds, dict):
            bound_left = int(bounds.get("left", 0))
            bound_top = int(bounds.get("top", 0))
            bound_right = bound_left + int(bounds.get("width", 0))
            bound_bottom = bound_top + int(bounds.get("height", 0))
        elif isinstance(bounds, (tuple, list)) and len(bounds) >= 4:
            bound_left, bound_top, bound_right, bound_bottom = map(int, bounds[:4])
        elif isinstance(bounds, (tuple, list)) and len(bounds) >= 2:
            bound_left = 0
            bound_top = 0
            bound_right = int(bounds[0])
            bound_bottom = int(bounds[1])
        else:
            return expanded

        x1 = max(bound_left, expanded["left"])
        y1 = max(bound_top, expanded["top"])
        x2 = min(bound_right, expanded["left"] + expanded["width"])
        y2 = min(bound_bottom, expanded["top"] + expanded["height"])
        if x2 <= x1 or y2 <= y1:
            return {
                "left": max(bound_left, left),
                "top": max(bound_top, top),
                "width": max(1, min(width, bound_right - bound_left)),
                "height": max(1, min(height, bound_bottom - bound_top)),
            }
        return {"left": x1, "top": y1, "width": x2 - x1, "height": y2 - y1}

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
        results, err = self.ocr_region(
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
        mode_list = self.config_getter().get("header_ocr_modes", [[4, "binary"], [3, "gray"]])
        for scale, mode in mode_list:
            results, err = self.ocr_region(
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


LocalOCRReader = LocalPaddleOCRReader
LocalEasyOCRReader = LocalPaddleOCRReader


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
        self._window_no_activate_enabled = False
        self._clickthrough_guard_job = None
        self._mouse_passthrough_hooked = False
        self._mouse_passthrough_old_proc = None
        self._mouse_passthrough_proc_ref = None
        self._ocr_warmup_started = False
        self._ocr_warmup_thread = None
        self.ocr = LocalOCRReader(lambda: self.config_data)
        self.middle_template = None
        self.middle_template_path = str(self.config_data.get("middle_template_path", "template_middle.png"))
        self.middle_template_threshold = float(self.config_data.get("middle_template_threshold", 0.58))
        self.load_middle_template()
        self.compact_species_text = None
        self.in_compact_mode = False
        self._settings_win = None
        self._compact_timed_hint_job = None
        self._compact_timed_hint_generation = 0
        self._mouse_passthrough_hooked = False
        self._mouse_passthrough_old_proc = None
        self._mouse_passthrough_proc_ref = None
        self._cursor_hidden = False

        self.root = tk.Tk()
        self.root.title("污染计数器")
        self._drag_data = {"x": 0, "y": 0, "win_x": 0, "win_y": 0}
        self._using_borderless = False
        self.apply_window_icon()
        win = self.config_data["window"]
        self.normal_size = (int(win["width"]), int(win["height"]))
        compact = self.config_data["compact_window"]
        self.compact_size = (max(300, int(compact["width"])), max(320, int(compact["height"])))
        self.root.geometry(f"{self.normal_size[0]}x{self.normal_size[1]}+{win['x']}+{win['y']}")
        self.root.configure(bg="#1a1023")
        self._apply_window_chrome()
        self._apply_initial_window_placement()
        self.root.resizable(False, False)
        self.root.bind("<Configure>", self.on_root_configure)
        self.root.attributes("-topmost", bool(self.config_data.get("always_on_top", True)))
        self.root.attributes("-alpha", max(0.30, min(1.00, float(self.config_data.get("window_alpha", 1.0)))))

        self.count_var = tk.StringVar()
        self.session_var = tk.StringVar()
        self.status_var = tk.StringVar(value="未启动")
        self.species_var = tk.StringVar(value="当前精灵: 无")
        self.pause_tip_var = tk.StringVar(value="")
        self.runtime_state_var = tk.StringVar(value="未启动｜可移动")
        _hk0 = self.config_data.get("hotkeys", {}) or {}
        _sk0 = str(_hk0.get("start", "7")).upper()
        _pk0 = str(_hk0.get("pause", "0")).upper()
        _ak0 = str(_hk0.get("add", "8")).upper()
        _uk0 = str(_hk0.get("sub", "9")).upper()
        _lk0 = str(_hk0.get("lock", "-")).upper()
        self.compact_hint_var = tk.StringVar(
            value=f"提示: {_sk0} 启/关  {_pk0} 暂停  {_lk0} 锁定/交互  {_ak0} 加污染  {_uk0} 减污染"
        )
        self.tip_title_var = tk.StringVar(value="请用热键启动")
        self.tip_detail_var = tk.StringVar()
        self.ocr_state_var = tk.StringVar(value="PaddleOCR状态: 未检查")

        hk = self.config_data["hotkeys"]
        self.add_key_var = tk.StringVar(value=hk.get("add", "8"))
        self.sub_key_var = tk.StringVar(value=hk.get("sub", "9"))
        self.start_key_var = tk.StringVar(value=hk.get("start", "7"))
        self.pause_key_var = tk.StringVar(value=hk.get("pause", "0"))
        self.lock_key_var = tk.StringVar(value=hk.get("lock", "-"))
        self.window_locked = False
        self.top_var = tk.BooleanVar(value=bool(self.config_data.get("always_on_top", True)))
        self.alpha_var = tk.DoubleVar(value=float(self.config_data.get("window_alpha", 1.0)))
        self.model_dir_var = tk.StringVar(
            value=self.config_data.get("paddleocr_model_dir") or "paddleocr_models"
        )
        self.resolution_var = tk.StringVar(value=str(self.config_data.get("active_resolution", "2560x1600_150缩放")))

        self._alpha_job = None
        self._last_applied_alpha = None
        self._last_bg_alpha = None
        self.main_hotkey_detail_label = None
        self.compact_hotkey_hint_label = None
        self.runtime_status_label = None
        self.main_status_label = None

        self.apply_resolution_preset(self.resolution_var.get(), show_message=False)

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.sync_memory_from_today()
        self.build_main_ui()
        self.register_hotkeys()
        self.update_display()
        self.root.after(80, self._ensure_movable_on_startup)
        self.root.after(500, self.update_ocr_state)
        self.root.after(1200, self._start_ocr_warmup)
        self.root.after(600, self._maybe_show_first_startup_tip)
        self.start_hotkey_polling()

    def _apply_initial_window_placement(self):
        """兼容旧配置：主窗口位置改由 build_main_ui 统一为屏幕左侧垂直居中。"""
        self.config_data["window_corner_placed_once"] = True

    def _maybe_show_first_startup_tip(self):
        if self.config_data.get("first_startup_tip_done", True):
            return
        messagebox.showinfo(
            "首次启动提示",
            "欢迎使用污染计数器。\n\n"
            "首次使用请先进入【设置】检查并修改分辨率，\n"
            "选择和你当前屏幕一致的预设后再开始使用。\n\n"
            "为正常截屏与全局热键，请使用管理员身份运行本程序。\n\n"
            "祝您早日出异色！！",
        )
        self.config_data["first_startup_tip_done"] = True
        self.save_config()

    def apply_window_icon(self):
        try:
            if ICON_FILE.exists():
                try:
                    self.root.iconbitmap(str(ICON_FILE))
                except Exception:
                    pass
        except Exception:
            pass

    def _get_window_hwnd(self):
        try:
            return int(self.root.winfo_id())
        except Exception:
            return 0

    def _set_cursor_hidden(self, hidden: bool):
        hidden = bool(hidden)
        if getattr(self, "_cursor_hidden", False) == hidden:
            return
        self._cursor_hidden = hidden
        try:
            self.root.configure(cursor="none" if hidden else "")
        except Exception:
            pass
        if sys.platform != "win32" or not hasattr(ctypes, "windll"):
            return
        try:
            user32 = ctypes.windll.user32
            if hidden:
                for _ in range(8):
                    if user32.ShowCursor(False) < 0:
                        break
            else:
                for _ in range(8):
                    if user32.ShowCursor(True) >= 0:
                        break
        except Exception:
            pass

    def _install_mouse_passthrough_hook(self):
        if sys.platform != "win32" or not hasattr(ctypes, "windll"):
            return
        if self._mouse_passthrough_hooked:
            return
        try:
            self.root.update_idletasks()
            hwnd = self._get_window_hwnd()
            if not hwnd:
                return

            GWL_WNDPROC = -4
            WM_NCHITTEST = 0x0084
            WM_MOUSEACTIVATE = 0x0021
            WM_SETCURSOR = 0x0020
            HTTRANSPARENT = -1
            MA_NOACTIVATEANDEAT = 4
            user32 = ctypes.windll.user32
            is_64 = ctypes.sizeof(ctypes.c_void_p) == 8
            LRESULT = ctypes.c_longlong if is_64 else ctypes.c_long
            WNDPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t)
            get_long = getattr(user32, "GetWindowLongPtrW", None) or user32.GetWindowLongW
            set_long = getattr(user32, "SetWindowLongPtrW", None) or user32.SetWindowLongW
            call_proc = getattr(user32, "CallWindowProcW")

            old_proc = int(get_long(hwnd, GWL_WNDPROC))
            if not old_proc:
                return

            @WNDPROC
            def _passthrough_proc(hWnd, msg, wParam, lParam):
                if msg == WM_NCHITTEST and bool(getattr(self, "window_locked", False)):
                    return HTTRANSPARENT
                if msg == WM_MOUSEACTIVATE and bool(getattr(self, "window_locked", False)):
                    return MA_NOACTIVATEANDEAT
                if msg == WM_SETCURSOR and bool(getattr(self, "window_locked", False)):
                    return 1
                return call_proc(ctypes.c_void_p(self._mouse_passthrough_old_proc), hWnd, msg, wParam, lParam)

            set_long(hwnd, GWL_WNDPROC, ctypes.cast(_passthrough_proc, ctypes.c_void_p).value)
            self._mouse_passthrough_old_proc = old_proc
            self._mouse_passthrough_proc_ref = _passthrough_proc
            self._mouse_passthrough_hooked = True
        except Exception:
            self._mouse_passthrough_hooked = False
            self._mouse_passthrough_old_proc = None
            self._mouse_passthrough_proc_ref = None

    def _remove_mouse_passthrough_hook(self):
        if sys.platform != "win32" or not hasattr(ctypes, "windll"):
            return
        if not self._mouse_passthrough_hooked:
            return
        try:
            hwnd = self._get_window_hwnd()
            if hwnd and self._mouse_passthrough_old_proc:
                GWL_WNDPROC = -4
                user32 = ctypes.windll.user32
                set_long = getattr(user32, "SetWindowLongPtrW", None) or user32.SetWindowLongW
                set_long(hwnd, GWL_WNDPROC, self._mouse_passthrough_old_proc)
        except Exception:
            pass
        finally:
            self._mouse_passthrough_hooked = False
            self._mouse_passthrough_old_proc = None
            self._mouse_passthrough_proc_ref = None

    def _apply_clickthrough_now(self, enabled: bool):
        enabled = bool(enabled)
        try:
            self.root.update_idletasks()
        except Exception:
            pass
        try:
            hwnd = self._get_window_hwnd()
            if not hwnd or not hasattr(ctypes, "windll"):
                return

            GWL_EXSTYLE = -20
            WS_EX_LAYERED = 0x00080000
            WS_EX_TRANSPARENT = 0x00000020
            WS_EX_TOOLWINDOW = 0x00000080
            WS_EX_APPWINDOW = 0x00040000
            WS_EX_NOACTIVATE = 0x08000000
            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            SWP_NOZORDER = 0x0004
            SWP_FRAMECHANGED = 0x0020
            SWP_NOACTIVATE = 0x0010
            LWA_ALPHA = 0x2

            user32 = ctypes.windll.user32
            get_long = getattr(user32, "GetWindowLongPtrW", None) or user32.GetWindowLongW
            set_long = getattr(user32, "SetWindowLongPtrW", None) or user32.SetWindowLongW

            ex_style = int(get_long(hwnd, GWL_EXSTYLE))
            ex_style |= WS_EX_LAYERED | WS_EX_TOOLWINDOW
            ex_style &= ~WS_EX_APPWINDOW
            if enabled:
                ex_style |= WS_EX_TRANSPARENT | WS_EX_NOACTIVATE
                self._install_mouse_passthrough_hook()
            else:
                ex_style &= ~WS_EX_TRANSPARENT
                ex_style &= ~WS_EX_NOACTIVATE
                self._remove_mouse_passthrough_hook()

            set_long(hwnd, GWL_EXSTYLE, ex_style)
            alpha_255 = max(76, min(255, int(round(self._clamp_alpha(self.alpha_var.get()) * 255))))
            ctypes.windll.user32.SetLayeredWindowAttributes(hwnd, 0, alpha_255, LWA_ALPHA)

            flags = SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED
            if enabled:
                flags |= SWP_NOACTIVATE
            ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, flags)
        except Exception:
            pass

    def set_clickthrough(self, enabled: bool):
        enabled = bool(enabled)
        self._apply_clickthrough_now(enabled)
        for delay in (60, 180, 420):
            try:
                self.root.after(delay, lambda e=enabled: self._apply_clickthrough_now(e))
            except Exception:
                pass

    def _cancel_clickthrough_guard(self):
        job = getattr(self, "_clickthrough_guard_job", None)
        if job is not None:
            try:
                self.root.after_cancel(job)
            except Exception:
                pass
        self._clickthrough_guard_job = None

    def _clickthrough_guard_tick(self):
        self._clickthrough_guard_job = None
        try:
            should_passthrough = bool(self.running) and bool(self.in_compact_mode) and bool(self.window_locked)
            if not should_passthrough:
                return
            self._apply_clickthrough_now(True)
            self._set_window_no_activate(True)
            self._clickthrough_guard_job = self.root.after(700, self._clickthrough_guard_tick)
        except Exception:
            pass

    def _start_clickthrough_guard(self):
        self._cancel_clickthrough_guard()
        if bool(self.running) and bool(self.in_compact_mode) and bool(self.window_locked):
            try:
                self._clickthrough_guard_job = self.root.after(250, self._clickthrough_guard_tick)
            except Exception:
                self._clickthrough_guard_job = None

    def _ensure_movable_on_startup(self):
        """启动后强制未锁定，便于拖移窗口。"""
        try:
            self.window_locked = False
            self.set_clickthrough(False)
            self._apply_running_window_mode()
            self.refresh_runtime_status()
        except Exception:
            pass

    def set_window_lock(self, locked: bool):
        if self.running and self.in_compact_mode:
            locked = True
        self.window_locked = bool(locked)
        self.set_clickthrough(self.window_locked)
        if self.window_locked:
            if self.running and self.in_compact_mode:
                self.status_var.set("运行中：只读")
            else:
                self.status_var.set("已锁定：只读")
            self._set_cursor_hidden(True)
        else:
            self.status_var.set("未锁定：可交互")
            self._set_cursor_hidden(False)
        self.refresh_runtime_status()
        self._apply_running_window_mode()
        self._start_clickthrough_guard()

    def toggle_window_lock(self):
        self.set_window_lock(not self.window_locked)

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
                cfg.setdefault("base_resolution", "2560x1600_150缩放")
                cfg.setdefault("active_resolution", "2560x1600_150缩放")
                cfg.setdefault("base_regions", {
                    "middle_region": dict(DEFAULT_CONFIG["middle_region"]),
                    "header_region": dict(DEFAULT_CONFIG["header_region"]),
                    "name_in_header": dict(DEFAULT_CONFIG["name_in_header"]),
                })
                merged_presets = dict(cfg.get("resolution_presets", {}) or {})
                merged_presets.update(_build_builtin_resolution_presets())
                cfg["resolution_presets"] = merged_presets
                cfg["name_in_header"]["width"] = max(20, int(cfg["name_in_header"].get("width", 204)))
                cfg["name_in_header"]["height"] = max(20, int(cfg["name_in_header"].get("height", 48)))
                cfg["name_in_header"]["left"] = max(0, int(cfg["name_in_header"].get("left", 99)))
                cfg["name_in_header"]["top"] = max(0, int(cfg["name_in_header"].get("top", 35)))
                cfg.setdefault("window_corner_placed_once", True)
                cfg.setdefault("first_startup_tip_done", True)
                cfg.setdefault("header_ocr_modes", DEFAULT_CONFIG.get("header_ocr_modes", [[4, "binary"], [3, "gray"]]))
                cfg.setdefault("github_api_latest_url", DEFAULT_CONFIG.get("github_api_latest_url", ""))
                legacy_paddleocr_model_dir = cfg.pop("easyocr_model_dir", None)
                paddleocr_model_dir = str(
                    cfg.get("paddleocr_model_dir") or legacy_paddleocr_model_dir or DEFAULT_CONFIG["paddleocr_model_dir"]
                ).strip() or DEFAULT_CONFIG["paddleocr_model_dir"]
                cfg["paddleocr_model_dir"] = paddleocr_model_dir
                cfg.pop("easyocr_languages", None)
                hk = dict(cfg.get("hotkeys") or {})
                for k, v in DEFAULT_CONFIG["hotkeys"].items():
                    hk.setdefault(k, v)
                cfg["hotkeys"] = hk
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
            model_dir = self.model_dir_var.get().strip() or "paddleocr_models"
            self.config_data["paddleocr_model_dir"] = model_dir
            self.config_data["active_resolution"] = str(self.resolution_var.get()).strip() or "2560x1600_150缩放"
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
                d.setdefault("species_total_counts", {})
                if not d["species_total_counts"]:
                    d["species_total_counts"] = aggregate_species_totals(
                        d.get("daily_species", {}), d.get("species_counts", {})
                    )
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

    def sync_today_from_memory(self, prefer_species_sum=False):
        day = today_str()
        if prefer_species_sum and self.species_counts:
            self.total_count = sum(int(v) for v in self.species_counts.values())
        self.daily_totals[day] = int(self.total_count)
        self.daily_species[day] = dict(self.species_counts)

    def sync_memory_from_today(self):
        day = today_str()
        if day in self.daily_totals:
            self.total_count = int(self.daily_totals.get(day, 0))
        if day in self.daily_species:
            self.species_counts = dict(self.daily_species.get(day, {}))

    def set_compact_hint(self, text):
        self.dismiss_compact_timed_hint()
        self._compact_timed_hint_generation += 1
        self.compact_hint_var.set(text)

    def dismiss_compact_timed_hint(self):
        if self._compact_timed_hint_job is not None:
            try:
                self.root.after_cancel(self._compact_timed_hint_job)
            except Exception:
                pass
            self._compact_timed_hint_job = None

    def show_compact_timed_hint(self, message, duration_ms=60_000):
        self.dismiss_compact_timed_hint()
        self._compact_timed_hint_generation += 1
        gen = self._compact_timed_hint_generation
        self.compact_hint_var.set(message)

        def _maybe_clear():
            self._compact_timed_hint_job = None
            if gen != self._compact_timed_hint_generation:
                return
            if self.compact_hint_var.get() == message:
                self.compact_hint_var.set("")

        self._compact_timed_hint_job = self.root.after(duration_ms, _maybe_clear)

    def clear_root(self):
        self.compact_species_text = None
        self.in_compact_mode = False
        for w in self.root.winfo_children():
            w.destroy()

    def _pill_button(self, master, text, command, *, donate=False, compact=False):
        font = UI_FONT_9 if compact else UI_FONT
        height = 30 if compact else 34
        radius = 10 if compact else 12
        if donate:
            return RoundedButton(
                master,
                text=text,
                command=command,
                font=UI_FONT_BOLD,
                height=height,
                radius=radius,
                fill="#c62828",
                fill_hover="#e53935",
                fill_pressed="#8b1515",
                fg="#fff8f8",
            )
        return RoundedButton(master, text=text, command=command, font=font, height=height, radius=radius)

    def _apply_window_chrome(self):
        borderless = bool(self.config_data.get("borderless_window", True))
        try:
            self.root.overrideredirect(borderless)
            self._using_borderless = borderless
        except Exception:
            self._using_borderless = False

    def _start_window_drag(self, event):
        try:
            self._drag_data["x"] = int(event.x_root)
            self._drag_data["y"] = int(event.y_root)
            self._drag_data["win_x"] = int(self.root.winfo_x())
            self._drag_data["win_y"] = int(self.root.winfo_y())
        except Exception:
            self._drag_data = {"x": 0, "y": 0, "win_x": 0, "win_y": 0}

    def _do_window_drag(self, event):
        if self.window_locked:
            return
        try:
            dx = int(event.x_root) - int(self._drag_data.get("x", 0))
            dy = int(event.y_root) - int(self._drag_data.get("y", 0))
            nx = int(self._drag_data.get("win_x", self.root.winfo_x())) + dx
            ny = int(self._drag_data.get("win_y", self.root.winfo_y())) + dy
            self.root.geometry(f"+{nx}+{ny}")
        except Exception:
            pass

    def _bind_drag_widgets(self, *widgets):
        for widget in widgets:
            if not widget:
                continue
            try:
                widget.bind("<ButtonPress-1>", self._start_window_drag, add="+")
                widget.bind("<B1-Motion>", self._do_window_drag, add="+")
            except Exception:
                pass

    def _create_titlebar_button(self, master, text, command, *, danger=False):
        fill = "#7b2230" if danger else "#33204a"
        fill_hover = "#a62d40" if danger else "#4a2e69"
        fill_pressed = "#641a27" if danger else "#261636"
        return RoundedButton(
            master,
            text=text,
            command=command,
            font=("Microsoft YaHei", 9, "bold"),
            height=24,
            radius=10,
            width_px=34,
            fill=fill,
            fill_hover=fill_hover,
            fill_pressed=fill_pressed,
            fg="#ffffff",
            bg_parent="#130b1b",
        )

    def _build_window_shell(self, *, title_text, subtitle_text=None, compact=False):
        self.clear_root()
        self._apply_window_chrome()
        try:
            self.root.resizable(False, False)
        except Exception:
            pass

        shell = tk.Frame(self.root, bg="#130b1b", highlightthickness=1, highlightbackground="#3f2b59")
        shell.pack(fill="both", expand=True, padx=1, pady=1)

        title_bar = tk.Frame(shell, bg="#130b1b", height=34 if compact else 38)
        title_bar.pack(fill="x", side="top")
        title_bar.pack_propagate(False)

        title_wrap = tk.Frame(title_bar, bg="#130b1b")
        title_wrap.pack(side="left", fill="x", expand=True, padx=(10, 6))

        title_label = tk.Label(
            title_wrap,
            text=title_text,
            font=("Microsoft YaHei", 11 if compact else 12, "bold"),
            fg="white",
            bg="#130b1b",
            anchor="w",
        )
        title_label.pack(anchor="w")

        sub_label = None

        right_box = tk.Frame(title_bar, bg="#130b1b")
        right_box.pack(side="right", padx=(4, 8), pady=5)

        self._create_titlebar_button(right_box, "×", self.on_close, danger=True).pack(side="left")

        body = tk.Frame(shell, bg="#1a1023")
        body.pack(fill="both", expand=True, padx=10 if compact else 12, pady=(8, 10 if compact else 12))

        self._bind_drag_widgets(shell, title_bar, title_wrap, title_label, sub_label)
        if self.window_locked:
            try:
                self.root.after(80, lambda: self.set_clickthrough(True))
                self.root.after(220, lambda: self.set_clickthrough(True))
            except Exception:
                pass
        return shell, body

    def _schedule_window_round_corners(self, window):
        try:
            window.after(120, lambda w=window: apply_dwm_rounded_corners(w))
        except Exception:
            pass

    def _main_window_left_center_xy(self, w, h):
        """主窗口：靠左留白，垂直大致居中（避开任务栏区域）。"""
        try:
            sw = int(self.root.winfo_screenwidth())
            sh = int(self.root.winfo_screenheight())
        except Exception:
            return 24, 80
        margin_l = 24
        margin_tb = 48
        x = max(8, margin_l)
        y = (sh - h) // 2
        y = max(margin_tb // 2, min(y, sh - h - margin_tb))
        return x, y

    def _compact_window_right_center_xy(self, w, h):
        """小窗：默认靠右居中偏上一点，给任务栏和屏幕边缘留一点余量。"""
        try:
            sw = int(self.root.winfo_screenwidth())
            sh = int(self.root.winfo_screenheight())
        except Exception:
            return 24, 80
        margin_r = 24
        margin_tb = 48
        upward_offset = 70
        x = max(8, sw - w - margin_r)
        y = (sh - h) // 2 - upward_offset
        y = max(margin_tb // 2, min(y, sh - h - margin_tb))
        return x, y

    def _dock_compact_window_right_center(self):
        """进入小窗时自动吸附到屏幕右侧居中。"""
        try:
            self.root.update_idletasks()
            w = max(260, int(self.root.winfo_width() or self.compact_size[0]))
            h = max(260, int(self.root.winfo_height() or self.compact_size[1]))
        except Exception:
            w, h = self.compact_size
        self.compact_size = (w, h)
        x, y = self._compact_window_right_center_xy(w, h)
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def _apply_main_window_fit_and_position(self, content_frame):
        """主界面：按内容请求宽高，并摆到屏幕左中。"""
        try:
            self.root.update_idletasks()
            root_w = int(self.root.winfo_reqwidth())
            root_h = int(self.root.winfo_reqheight())
            fw = int(content_frame.winfo_reqwidth()) + 24
            fh = int(content_frame.winfo_reqheight()) + 24
            req_w = max(root_w, fw)
            req_h = max(root_h, fh)
        except Exception:
            req_w, req_h = 400, 520
        fit_w = max(320, req_w)
        fit_h = max(340, req_h)
        self.normal_size = (fit_w, fit_h)
        x, y = self._main_window_left_center_xy(fit_w, fit_h)
        self.root.geometry(f"{fit_w}x{fit_h}+{x}+{y}")
        try:
            wd = self.config_data["window"]
            wd["width"] = fit_w
            wd["height"] = fit_h
            wd["x"] = x
            wd["y"] = y
            self.save_config()
        except Exception:
            pass

    def set_window_size(self, width, height):
        x = self.root.winfo_x()
        y = self.root.winfo_y()
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        self.root.update_idletasks()

    def parse_resolution_text(self, text):
        try:
            clean = str(text).lower().replace(" ", "")
            clean = clean.split("_")[0]
            parts = clean.split("x")
            if len(parts) != 2:
                raise ValueError
            return max(1, int(parts[0])), max(1, int(parts[1]))
        except Exception:
            return 2560, 1600

    def scale_region_from_base(self, region, scale_x, scale_y):
        return {
            "left": int(round(float(region.get("left", 0)) * scale_x)),
            "top": int(round(float(region.get("top", 0)) * scale_y)),
            "width": max(1, int(round(float(region.get("width", 1)) * scale_x))),
            "height": max(1, int(round(float(region.get("height", 1)) * scale_y))),
        }

    def apply_resolution_preset(self, preset=None, show_message=True):
        preset = str(preset or self.resolution_var.get()).strip() or "2560x1600_150缩放"
        self.resolution_var.set(preset)

        presets = self.config_data.get("resolution_presets", {}) or {}
        if preset in presets:
            region_pack = presets[preset]
            self.config_data["middle_region"] = dict(region_pack.get("middle_region", self.config_data.get("middle_region", DEFAULT_CONFIG["middle_region"])))
            self.config_data["header_region"] = dict(region_pack.get("header_region", self.config_data.get("header_region", DEFAULT_CONFIG["header_region"])))
            self.config_data["name_in_header"] = dict(region_pack.get("name_in_header", self.config_data.get("name_in_header", DEFAULT_CONFIG["name_in_header"])))
            mode_text = "专用预设"
        else:
            base_w, base_h = self.parse_resolution_text(self.config_data.get("base_resolution", "2560x1600"))
            target_w, target_h = self.parse_resolution_text(preset)
            scale_x = target_w / max(base_w, 1)
            scale_y = target_h / max(base_h, 1)

            base_regions = self.config_data.get("base_regions", {})
            for key in ("middle_region", "header_region", "name_in_header"):
                region = base_regions.get(key, DEFAULT_CONFIG[key])
                self.config_data[key] = self.scale_region_from_base(region, scale_x, scale_y)
            mode_text = "按比例缩放"

        # 窗口化模式：将游戏窗口在屏幕上的偏移叠加到 middle_region / header_region
        offset = self.config_data.get("window_offset", None)
        if offset and (offset.get("x", 0) != 0 or offset.get("y", 0) != 0):
            ox, oy = int(offset.get("x", 0)), int(offset.get("y", 0))
            for key in ("middle_region", "header_region"):
                r = self.config_data[key]
                self.config_data[key] = {
                    "left": r["left"] + ox,
                    "top": r["top"] + oy,
                    "width": r["width"],
                    "height": r["height"],
                }
            mode_text += "（窗口化偏移）"

        self.config_data["active_resolution"] = preset
        self.save_config()
        if show_message:
            messagebox.showinfo("分辨率切换", f"已切换到 {preset}（{mode_text}）")

    def on_root_configure(self, _event=None):
        try:
            if self.in_compact_mode:
                w = max(260, int(self.root.winfo_width()))
                h = max(260, int(self.root.winfo_height()))
                self.compact_size = (w, h)
                self.config_data["compact_window"]["width"] = w
                self.config_data["compact_window"]["height"] = h
            else:
                w = max(320, int(self.root.winfo_width()))
                h = max(300, int(self.root.winfo_height()))
                self.normal_size = (w, h)
                self.config_data["window"]["width"] = w
                self.config_data["window"]["height"] = h
                self.config_data["window"]["x"] = int(self.root.winfo_x())
                self.config_data["window"]["y"] = int(self.root.winfo_y())
        except Exception:
            pass


    def show_donate_info(self):
        donate_id = "15206290688"
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(donate_id)
            self.root.update()
            messagebox.showinfo(
                "打赏作者",
                f"感谢支持\n\n支付宝：{donate_id}\n\n账号已复制到剪贴板"
            )
        except Exception:
            messagebox.showinfo(
                "打赏作者",
                f"感谢支持\n\n支付宝：{donate_id}"
            )


    def get_current_version(self):
        return str(self.config_data.get("app_version", "v1.1.0"))

    def compare_versions(self, current, latest):
        def parse(v):
            nums = re.findall(r"\d+", str(v))
            return tuple(int(x) for x in nums[:4]) if nums else (0,)
        c = parse(current)
        l = parse(latest)
        max_len = max(len(c), len(l))
        c = c + (0,) * (max_len - len(c))
        l = l + (0,) * (max_len - len(l))
        if c < l:
            return -1
        if c > l:
            return 1
        return 0

    def open_release_page(self):
        url = str(self.config_data.get("release_page_url", "")).strip()
        if not url:
            messagebox.showwarning("检查更新", "未配置下载页面链接")
            return
        try:
            webbrowser.open(url)
        except Exception as e:
            messagebox.showerror("检查更新", f"无法打开链接\n\n{e}")

    def fetch_remote_version_json(self):
        info_url = str(self.config_data.get("update_info_url", "")).strip()
        if not info_url:
            return None
        try:
            req = urllib.request.Request(info_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception:
            return None

    def show_update_log_window(self):
        top = tk.Toplevel(self.root)
        top.title("更新日志")
        top.attributes("-topmost", True)
        top.geometry("560x420")
        top.configure(bg="#171021")
        top.resizable(True, True)

        tk.Label(
            top,
            text="从远程版本信息加载的更新说明",
            font=("Microsoft YaHei", 11, "bold"),
            fg="white",
            bg="#171021",
        ).pack(anchor="w", padx=12, pady=(10, 4))

        body = scrolledtext.ScrolledText(
            top,
            font=("Microsoft YaHei", 10),
            bg="#221532",
            fg="#f0e7ff",
            insertbackground="white",
            wrap="word",
            relief="flat",
            height=16,
        )
        body.pack(fill="both", expand=True, padx=12, pady=6)
        body.insert("1.0", "正在加载更新日志…")
        body.config(state="disabled")

        def apply_text(s):
            body.config(state="normal")
            body.delete("1.0", "end")
            body.insert("1.0", s)
            body.config(state="disabled")

        def worker():
            data = self.fetch_remote_version_json()
            if not str(self.config_data.get("update_info_url", "")).strip():
                msg = "未在配置中填写更新地址（update_info_url）。"
            elif data is None:
                msg = "无法获取远程版本信息，请检查网络或地址是否有效。"
            else:
                ver = str(data.get("version", "")).strip() or "（未标注）"
                notes = str(data.get("notes", "")).strip()
                cur = self.get_current_version()
                msg = f"本机配置版本：{cur}\n远端标注版本：{ver}\n\n—— 更新说明 ——\n\n{notes if notes else '（远端未提供说明文本）'}"
            self.root.after(0, lambda: apply_text(msg))

        threading.Thread(target=worker, daemon=True).start()

        btn_row = tk.Frame(top, bg="#171021")
        btn_row.pack(fill="x", pady=(0, 10))
        RoundedButton(
            btn_row,
            text="关闭",
            command=top.destroy,
            bg_parent="#171021",
        ).pack(side="right", padx=12)
        RoundedButton(
            btn_row,
            text="清空并存档",
            command=self.confirm_archive_and_clear_today,
            bg_parent="#171021",
        ).pack(side="right", padx=(0, 8))
        self._schedule_window_round_corners(top)

    def check_for_updates(self):
        current_version = self.get_current_version()
        info_url = str(self.config_data.get("update_info_url", "")).strip()
        release_url = str(self.config_data.get("release_page_url", "")).strip()
        if not info_url:
            messagebox.showwarning("检查更新", "未配置更新地址")
            return
        try:
            req = urllib.request.Request(
                info_url,
                headers={"User-Agent": "Mozilla/5.0"}
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            latest_version = str(data.get("version", "")).strip() or current_version
            notes = str(data.get("notes", "")).strip()
            download_url = str(data.get("download_url", "")).strip() or release_url

            cmp_result = self.compare_versions(current_version, latest_version)
            if cmp_result < 0:
                msg = f"当前版本：{current_version}\n最新版本：{latest_version}"
                if notes:
                    msg += f"\n\n更新内容：\n{notes}"
                msg += "\n\n是否前往下载页面？"
                if messagebox.askyesno("发现新版本", msg):
                    if download_url:
                        webbrowser.open(download_url)
            else:
                messagebox.showinfo("检查更新", f"当前已是最新版本\n\n当前版本：{current_version}")
                self.root.after(150, self.show_update_log_window)
        except urllib.error.URLError as e:
            messagebox.showerror("检查更新", f"网络连接失败\n\n{e}")
        except Exception as e:
            messagebox.showerror("检查更新", f"检查更新失败\n\n{e}")

    def _close_settings_dialog(self):
        w = getattr(self, "_settings_win", None)
        if w is not None:
            try:
                if w.winfo_exists():
                    w.destroy()
            except Exception:
                pass
        self._settings_win = None

    def open_settings_dialog(self):
        if getattr(self, "_settings_win", None):
            try:
                if self._settings_win.winfo_exists():
                    self._settings_win.lift()
                    self._settings_win.focus_force()
                    return
            except Exception:
                self._settings_win = None

        top = tk.Toplevel(self.root)
        self._settings_win = top
        top.title("设置")
        top.configure(bg="#1a1023")
        top.minsize(400, 260)
        try:
            top.transient(self.root)
        except Exception:
            pass

        def on_close():
            self._settings_win = None
            try:
                top.destroy()
            except Exception:
                pass

        top.protocol("WM_DELETE_WINDOW", on_close)

        outer = tk.Frame(top, bg="#1a1023")
        outer.pack(fill="x", expand=False, padx=8, pady=8)
        self._build_settings_form(outer)
        self.refresh_hotkey_tip()
        top.update_idletasks()
        try:
            req_w = max(400, int(top.winfo_reqwidth()))
            req_h = max(260, int(top.winfo_reqheight()))
            top.geometry(f"{req_w}x{req_h}")
        except Exception:
            top.geometry("520x380")
        self._schedule_window_round_corners(top)

    def _build_settings_form(self, frame):
        """设置窗口：软件更新、热键、分辨率、透明度等（打赏/版本/启动/热键提示在主界面）。"""
        update_row = tk.Frame(frame, bg="#1a1023")
        update_row.pack(anchor="nw", fill="x", pady=(0, 4))
        tk.Label(
            update_row,
            text="软件更新",
            fg="#bfa7ee",
            bg="#1a1023",
            font=UI_FONT_9,
        ).pack(side="left", padx=(0, 6))
        self._pill_button(update_row, text="检查更新", command=self.check_for_updates).pack(side="left", padx=(0, 4))
        self._pill_button(update_row, text="更新日志", command=self.show_update_log_window).pack(side="left", padx=(0, 4))
        self._pill_button(update_row, text="打开发布页", command=self.open_release_page).pack(side="left", padx=(0, 4))

        hk_entry_kw = dict(
            width=6,
            justify="center",
            font=UI_FONT,
            relief=tk.FLAT,
            bd=0,
            bg="#2a1f38",
            fg="#f0e7ff",
            highlightthickness=1,
            highlightbackground="#4a3d5c",
            highlightcolor="#7c6b94",
            insertbackground="#f0e7ff",
        )

        tk.Label(
            frame,
            text="全局热键",
            fg="#bfa7ee",
            bg="#1a1023",
            font=UI_FONT_9,
        ).pack(anchor="w", pady=(2, 3))

        row_start_pause = tk.Frame(frame, bg="#1a1023")
        row_start_pause.pack(anchor="w", fill="x", pady=(0, 4))

        grp_start = tk.Frame(row_start_pause, bg="#1a1023")
        grp_start.pack(side="left", padx=(0, 14))
        tk.Label(grp_start, text="启/关", fg="white", bg="#1a1023", font=UI_FONT).pack(side="left", padx=(0, 4))
        tk.Entry(grp_start, textvariable=self.start_key_var, **hk_entry_kw).pack(side="left", padx=(0, 4))
        self._pill_button(grp_start, text="录制", command=lambda: self.record_hotkey("start")).pack(side="left")

        grp_pause = tk.Frame(row_start_pause, bg="#1a1023")
        grp_pause.pack(side="left", padx=(0, 14))
        tk.Label(grp_pause, text="暂停", fg="white", bg="#1a1023", font=UI_FONT).pack(side="left", padx=(0, 4))
        tk.Entry(grp_pause, textvariable=self.pause_key_var, **hk_entry_kw).pack(side="left", padx=(0, 4))
        self._pill_button(grp_pause, text="录制", command=lambda: self.record_hotkey("pause")).pack(side="left")

        self._pill_button(row_start_pause, text="应用热键", command=self.apply_hotkey_changes).pack(side="left", padx=(10, 0))

        row_add_sub = tk.Frame(frame, bg="#1a1023")
        row_add_sub.pack(anchor="w", fill="x", pady=(0, 6))

        grp_add = tk.Frame(row_add_sub, bg="#1a1023")
        grp_add.pack(side="left", padx=(0, 14))
        tk.Label(grp_add, text="+污染", fg="white", bg="#1a1023", font=UI_FONT).pack(side="left", padx=(0, 4))
        tk.Entry(grp_add, textvariable=self.add_key_var, **hk_entry_kw).pack(side="left", padx=(0, 4))
        self._pill_button(grp_add, text="录制", command=lambda: self.record_hotkey("add")).pack(side="left")

        grp_sub = tk.Frame(row_add_sub, bg="#1a1023")
        grp_sub.pack(side="left")
        tk.Label(grp_sub, text="-污染", fg="white", bg="#1a1023", font=UI_FONT).pack(side="left", padx=(0, 4))
        tk.Entry(grp_sub, textvariable=self.sub_key_var, **hk_entry_kw).pack(side="left", padx=(0, 4))
        self._pill_button(grp_sub, text="录制", command=lambda: self.record_hotkey("sub")).pack(side="left")

        row_lock = tk.Frame(frame, bg="#1a1023")
        row_lock.pack(anchor="w", fill="x", pady=(0, 4))
        tk.Label(row_lock, text="锁定/互动", fg="white", bg="#1a1023", font=UI_FONT).pack(side="left", padx=(0, 4))
        tk.Entry(row_lock, textvariable=self.lock_key_var, **hk_entry_kw).pack(side="left", padx=(0, 4))
        self._pill_button(row_lock, text="录制", command=lambda: self.record_hotkey("lock")).pack(side="left")

        row5 = tk.Frame(frame, bg="#1a1023")
        row5.pack(pady=(2, 3))
        tk.Checkbutton(
            row5,
            text="始终置顶",
            variable=self.top_var,
            command=self.apply_topmost,
            fg="white",
            bg="#1a1023",
            selectcolor="#1a1023",
            activebackground="#1a1023",
            activeforeground="white",
            font=UI_FONT,
        ).pack(side="left", padx=2)
        tk.Label(row5, text="透明度", fg="white", bg="#1a1023", font=UI_FONT).pack(side="left", padx=(6, 3))
        tk.Scale(
            row5,
            from_=0.0,
            to=1.0,
            resolution=0.01,
            orient="horizontal",
            length=120,
            variable=self.alpha_var,
            command=self.apply_alpha,
            fg="white",
            bg="#1a1023",
            highlightthickness=0,
            troughcolor="#3a2d4a",
            activebackground="#1a1023",
        ).pack(side="left", padx=2)

        row6 = tk.Frame(frame, bg="#1a1023")
        row6.pack(pady=(0, 2))
        tk.Label(row6, text="分辨率", fg="white", bg="#1a1023", font=UI_FONT).pack(side="left", padx=(0, 4))
        # 可编辑输入框，支持任意分辨率（如 1280x720、窗口化等）
        res_entry = tk.Entry(
            row6, textvariable=self.resolution_var, font=UI_FONT,
            width=18, bg="#2a1f3d", fg="white", insertbackground="white",
            relief=tk.FLAT, highlightthickness=1, highlightbackground="#4a3d5c",
        )
        res_entry.pack(side="left")
        # 下拉历史按钮
        self._res_dropdown_btn = tk.Button(
            row6, text="▼", font=UI_FONT_8, bg="#2a1f3d", fg="white",
            relief=tk.FLAT, bd=0, cursor="hand2",
            command=lambda: self._show_resolution_dropdown(res_entry),
        )
        self._res_dropdown_btn.pack(side="left", padx=(1, 4))
        self._pill_button(row6, text="应用", command=self.on_apply_resolution).pack(side="left", padx=(0, 4))
        self._pill_button(row6, text="分辨率适配", command=self.on_detect_screen_resolution).pack(side="left", padx=(0, 4))
        self._pill_button(row6, text="检测游戏窗口", command=self.on_detect_game_window).pack(side="left", padx=(0, 2))

        row6b = tk.Frame(frame, bg="#1a1023")
        row6b.pack(pady=(0, 4))
        self._window_mode_label = tk.Label(
            row6b, text="", fg="#9f8cc9", bg="#1a1023", font=UI_FONT_8, wraplength=480, justify="left"
        )
        self._window_mode_label.pack(side="left")

        bottom_box = tk.Frame(frame, bg="#1a1023")
        bottom_box.pack(fill="x", pady=(6, 0), anchor="n")

        tk.Label(
            bottom_box,
            text="原创作者：小丑鱼   抖音号：conflicto834",
            fg="#9f8cc9",
            bg="#1a1023",
            font=UI_FONT_9,
        ).pack(pady=(1, 0))

        tk.Label(
            bottom_box,
            text="GitHub：https://github.com/YUZE04/Roco-pollution-counter",
            fg="#8ab4ff",
            bg="#1a1023",
            font=UI_FONT_8,
            wraplength=440,
            justify="center",
        ).pack(pady=(1, 0))

    def build_main_ui(self):
        self._close_settings_dialog()
        self.in_compact_mode = False
        self.root.title("污染计数器")

        shell, frame = self._build_window_shell(
            title_text="污染计数器",
            subtitle_text=None,
            compact=False,
        )

        top_bar = tk.Frame(frame, bg="#1a1023")
        top_bar.pack(fill="x", pady=(0, 8))
        self._pill_button(top_bar, text="打赏作者", command=self.show_donate_info, donate=True).pack(side="left", padx=(0, 8))
        tk.Label(
            top_bar,
            text=f"当前版本：{self.get_current_version()}",
            fg="#d7c5ff",
            bg="#1a1023",
            font=UI_FONT_9,
        ).pack(side="left", padx=(0, 12))
        tk.Frame(top_bar, bg="#1a1023").pack(side="left", expand=True, fill="x")
        self._pill_button(top_bar, text="详情", command=self.show_species_stats).pack(side="right", padx=(4, 0))
        self._pill_button(top_bar, text="设置", command=self.open_settings_dialog).pack(side="right", padx=(4, 0))

        card = tk.Frame(frame, bg="#241537", highlightthickness=1, highlightbackground="#3f2b59")
        card.pack(fill="both", expand=True)

        tk.Label(card, text="今日总污染数", font=UI_FONT_TITLE, fg="white", bg="#241537").pack(pady=(14, 6))
        tk.Label(card, textvariable=self.count_var, font=UI_FONT_COUNT, fg="#ffd66b", bg="#241537").pack()
        tk.Label(card, textvariable=self.session_var, font=UI_FONT, fg="#d7c5ff", bg="#241537").pack(pady=(4, 0))
        self.main_status_label = tk.Label(card, textvariable=self.status_var, font=UI_FONT, fg="#d7c5ff", bg="#241537")
        self.main_status_label.pack(pady=(4, 0))
        tk.Label(card, textvariable=self.species_var, font=UI_FONT, fg="#a8ffde", bg="#241537").pack(pady=(4, 0))

        tk.Label(
            card,
            textvariable=self.tip_title_var,
            fg="#ffcf5a",
            bg="#241537",
            font=("Microsoft YaHei UI", 11, "bold"),
            justify="center",
        ).pack(pady=(8, 2))
        self.main_hotkey_detail_label = tk.Label(
            card,
            textvariable=self.tip_detail_var,
            fg=LOCK_IDLE_PURPLE,
            bg="#241537",
            font=UI_FONT_9,
            wraplength=460,
            justify="center",
        )
        self.main_hotkey_detail_label.pack(pady=(0, 14))

        self.refresh_hotkey_tip()
        self.apply_background_opacity(float(self.alpha_var.get()))
        self._apply_main_window_fit_and_position(shell)
        self._schedule_window_round_corners(self.root)

    def build_compact_ui(self):
        self.in_compact_mode = True
        self.root.title("污染计数器")
        shell, outer = self._build_window_shell(
            title_text="污染计数器",
            subtitle_text=None,
            compact=True,
        )
        self.set_window_size(*self.compact_size)
        outer.grid_rowconfigure(5, weight=1)
        outer.grid_columnconfigure(0, weight=1)

        status_strip = tk.Frame(outer, bg="#241537", highlightthickness=1, highlightbackground="#3f2b59")
        status_strip.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        status_strip.grid_columnconfigure(0, weight=1)
        status_strip.grid_columnconfigure(1, weight=0)
        self.runtime_status_label = tk.Label(
            status_strip,
            textvariable=self.runtime_state_var,
            font=("Microsoft YaHei", 10, "bold"),
            fg=LOCK_IDLE_LAVENDER,
            bg="#241537",
            anchor="w",
            justify="left",
            wraplength=176,
        )
        self.runtime_status_label.grid(row=0, column=0, sticky="ew", padx=(10, 6), pady=7)
        status_btns = tk.Frame(status_strip, bg="#241537")
        status_btns.grid(row=0, column=1, sticky="e", padx=(0, 8), pady=4)
        self._pill_button(status_btns, text="详情", command=self.show_species_stats, compact=True).pack(side="right", padx=(0, 4))
        self._pill_button(status_btns, text="设置", command=self.open_settings_dialog, compact=True).pack(side="right")

        count_card = tk.Frame(outer, bg="#241537", highlightthickness=1, highlightbackground="#3f2b59")
        count_card.grid(row=1, column=0, sticky="ew")
        count_card.grid_columnconfigure(0, weight=0)
        count_card.grid_columnconfigure(1, weight=1)
        tk.Label(
            count_card,
            text="今日总污染数",
            font=("Microsoft YaHei", 11, "bold"),
            fg="white",
            bg="#241537",
            anchor="w",
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=10, pady=(10, 2))
        tk.Label(
            count_card,
            textvariable=self.count_var,
            font=UI_FONT_COUNT_COMPACT,
            fg="#ffd66b",
            bg="#241537",
            anchor="w",
        ).grid(row=1, column=0, sticky="w", padx=(10, 6), pady=(0, 10))
        count_meta = tk.Frame(count_card, bg="#241537")
        count_meta.grid(row=1, column=1, sticky="ew", padx=(18, 10), pady=(0, 8))
        tk.Label(
            count_meta,
            textvariable=self.session_var,
            font=UI_FONT_11,
            fg="#f0e7ff",
            bg="#241537",
            anchor="w",
            justify="left",
        ).pack(anchor="w", padx=(6, 0), pady=(6, 4))
        tk.Label(
            count_meta,
            textvariable=self.species_var,
            font=UI_FONT_11,
            fg="#a8ffde",
            bg="#241537",
            anchor="w",
            justify="left",
        ).pack(anchor="w", padx=(6, 0))

        hk = self.config_data["hotkeys"]
        hotkey_card = tk.Frame(outer, bg="#241537", highlightthickness=1, highlightbackground="#3f2b59")
        hotkey_card.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        hotkey_text = f"启/关 {hk['start']}   暂停 {hk['pause']}   锁/交 {hk.get('lock', '=')}   +污 {hk['add']}   -污 {hk['sub']}"
        tk.Label(hotkey_card, text=hotkey_text, font=UI_FONT_9, fg="#d7c5ff", bg="#241537", anchor="w").pack(anchor="w", padx=10, pady=(8, 2))
        self.compact_hotkey_hint_label = tk.Label(hotkey_card, textvariable=self.compact_hint_var, font=UI_FONT_9, fg="#ffd66b", bg="#241537", anchor="w", justify="left", wraplength=340)
        self.compact_hotkey_hint_label.pack(anchor="w", padx=10, pady=(0, 8))

        species_card = tk.Frame(outer, bg="#241537", highlightthickness=1, highlightbackground="#3f2b59")
        species_card.grid(row=5, column=0, sticky="nsew", pady=(8, 0))
        species_card.grid_rowconfigure(1, weight=1)
        species_card.grid_columnconfigure(0, weight=1)
        species_hdr = tk.Frame(species_card, bg="#241537")
        species_hdr.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        tk.Label(species_hdr, text="精灵统计总表", fg="white", bg="#241537", font=("Microsoft YaHei", 11, "bold")).pack(side="left", anchor="w")
        tk.Frame(species_hdr, bg="#241537").pack(side="left", expand=True, fill="x")
        self._pill_button(species_hdr, text="清空", command=self.confirm_clear_species_summary, compact=True).pack(side="right")

        list_outer = tk.Frame(species_card, bg="#241537")
        list_outer.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        list_outer.grid_rowconfigure(0, weight=1)
        list_outer.grid_columnconfigure(0, weight=1)

        self.compact_species_text = tk.Listbox(
            list_outer,
            height=12,
            font=UI_FONT,
            bg="#1a1023",
            fg="#d7f7ff",
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground="#4a3d5c",
            activestyle="none",
            selectbackground="#33204a",
            selectforeground="#d7f7ff",
            exportselection=False,
        )
        self.compact_species_text.grid(row=0, column=0, sticky="nsew")
        self.compact_species_scrollbar = tk.Scrollbar(list_outer, orient="vertical", command=self.compact_species_text.yview)
        self.compact_species_scrollbar.grid(row=0, column=1, sticky="ns")
        self.compact_species_text.config(yscrollcommand=self.compact_species_scrollbar.set)
        self.refresh_runtime_status()
        self.apply_background_opacity(float(self.alpha_var.get()))
        self.root.after(10, self._dock_compact_window_right_center)
        self._schedule_window_round_corners(self.root)

    def _set_window_no_activate(self, enabled):
        enabled = bool(enabled)
        if self._window_no_activate_enabled == enabled:
            return
        self._window_no_activate_enabled = enabled
        if not hasattr(ctypes, "windll"):
            return
        try:
            hwnd = int(self.root.winfo_id())
            GWL_EXSTYLE = -20
            WS_EX_NOACTIVATE = 0x08000000
            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            SWP_NOZORDER = 0x0004
            SWP_FRAMECHANGED = 0x0020
            SWP_NOACTIVATE = 0x0010
            user32 = ctypes.windll.user32
            style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            if enabled:
                style |= WS_EX_NOACTIVATE
            else:
                style &= ~WS_EX_NOACTIVATE
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
            flags = SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED
            if enabled:
                flags |= SWP_NOACTIVATE
            user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, flags)
        except Exception:
            pass

    def _apply_running_window_mode(self):
        ga = bool(self.config_data.get("game_mode_no_activate", True))
        enabled = ga and bool(self.running) and bool(self.in_compact_mode)
        try:
            self.root.after(0, lambda: self._set_window_no_activate(enabled))
            self.root.after(120, lambda: self._set_window_no_activate(enabled))
        except Exception:
            self._set_window_no_activate(enabled)
        if self.running and self.in_compact_mode:
            self.set_clickthrough(True)

    def enter_compact_mode(self):
        self._ui_switching = True
        self._close_settings_dialog()
        self.build_compact_ui()
        self.update_display()
        self.root.update_idletasks()
        self.apply_background_opacity(float(self.alpha_var.get()))
        self._dock_compact_window_right_center()
        if self.running and self.in_compact_mode:
            self.set_clickthrough(True)
        self._apply_running_window_mode()
        self._start_clickthrough_guard()
        self.root.after(260, lambda: setattr(self, "_ui_switching", False))

    def apply_compact_alpha(self):
        if not self.running or not self.in_compact_mode:
            return
        self.apply_background_opacity(float(self.alpha_var.get()))

    def adjust_compact_height(self, delta):
        if not self.in_compact_mode:
            return
        try:
            w = max(300, int(self.root.winfo_width() or self.compact_size[0]))
            h = max(320, int(self.root.winfo_height() or self.compact_size[1]))
        except Exception:
            w, h = self.compact_size
        new_h = max(320, min(760, h + int(delta)))
        self.compact_size = (w, new_h)
        self.config_data["compact_window"]["width"] = w
        self.config_data["compact_window"]["height"] = new_h
        self.set_window_size(w, new_h)
        self.save_config()

    def enter_settings_mode(self):
        self._ui_switching = True
        self.in_compact_mode = False
        self.build_main_ui()
        self.set_window_size(self.normal_size[0], max(self.normal_size[1], 320))
        self.update_display()
        self.apply_background_opacity(float(self.alpha_var.get()))
        self._set_window_no_activate(False)
        try:
            self.root.deiconify()
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
            self.ocr_state_var.set("PaddleOCR状态: 已就绪")
        elif self.ocr.loading:
            self.ocr_state_var.set("PaddleOCR状态: 加载中")
        elif self.ocr.error:
            self.ocr_state_var.set("PaddleOCR状态: " + self.ocr.error[:60])
        else:
            self.ocr_state_var.set("PaddleOCR状态: 未检查")
        self.root.after(800, self.update_ocr_state)

    def apply_topmost(self):
        self.root.attributes("-topmost", bool(self.top_var.get()))
        self.save_config()

    def on_apply_resolution(self):
        self.apply_resolution_preset(self.resolution_var.get(), show_message=True)
        self.save_ocr_capture_positions("apply_resolution")
        self._update_window_mode_label()

    def _update_window_mode_label(self):
        """更新分辨率模式说明标签。"""
        try:
            label = getattr(self, "_window_mode_label", None)
            if label is None:
                return
            cfg = self.config_data
            offset = cfg.get("window_offset", None)
            if offset and (offset.get("x", 0) != 0 or offset.get("y", 0) != 0):
                client_size = cfg.get("window_client_size", {}) or {}
                client_text = ""
                if client_size.get("w") and client_size.get("h"):
                    client_text = f"  客户区 {client_size.get('w')}x{client_size.get('h')}"
                label.config(
                    text=f"窗口化模式  偏移 ({offset['x']}, {offset['y']})  "
                         f"游戏区域 {offset.get('w', '?')}x{offset.get('h', '?')}{client_text}",
                    fg="#6dffb3",
                )
            else:
                label.config(text="全屏模式", fg="#9f8cc9")
        except Exception:
            pass

    def _show_resolution_dropdown(self, entry_widget):
        """在输入框下方弹出常用分辨率列表。"""
        presets = list((self.config_data.get("resolution_presets", {}) or {}).keys())
        builtins = ["1920x1080", "2560x1440", "2560x1600_150缩放", "1280x720", "3840x2160"]
        options = list(dict.fromkeys(presets + [x for x in builtins if x not in presets]))

        popup = tk.Toplevel(self.root)
        popup.overrideredirect(True)
        popup.attributes("-topmost", True)
        popup.configure(bg="#2a1f3d")

        x = entry_widget.winfo_rootx()
        y = entry_widget.winfo_rooty() + entry_widget.winfo_height()
        popup.geometry(f"+{x}+{y}")

        def pick(val):
            self.resolution_var.set(val)
            popup.destroy()

        for opt in options:
            btn = tk.Button(
                popup, text=opt, font=UI_FONT_9, bg="#2a1f3d", fg="white",
                relief=tk.FLAT, anchor="w", padx=8, pady=2, cursor="hand2",
                activebackground="#4a3d5c", activeforeground="white",
                command=lambda v=opt: pick(v),
            )
            btn.pack(fill="x")

        popup.bind("<FocusOut>", lambda _e: popup.destroy())
        popup.focus_set()

    def on_detect_screen_resolution(self):
        """自动读取当前主屏幕分辨率并填入输入框。"""
        try:
            import ctypes
            user32 = ctypes.windll.user32
            user32.SetProcessDPIAware()
            w = user32.GetSystemMetrics(0)
            h = user32.GetSystemMetrics(1)
        except Exception:
            try:
                w = self.root.winfo_screenwidth()
                h = self.root.winfo_screenheight()
            except Exception:
                messagebox.showerror("适配失败", "无法获取当前分辨率")
                return

        res_str = f"{w}x{h}"
        self.resolution_var.set(res_str)
        # 清除窗口偏移（全屏模式）
        self.config_data.pop("window_offset", None)
        self.config_data.pop("window_client_size", None)
        self.apply_resolution_preset(res_str, show_message=False)
        self.save_ocr_capture_positions("detect_screen_resolution")
        self._update_window_mode_label()
        messagebox.showinfo("分辨率适配", f"已识别当前分辨率：{res_str}\n已填入输入框，点击「应用」生效。")

    def _resolve_game_window_client_info(self):
        """尝试定位游戏窗口并返回客户区屏幕坐标。失败返回 None。"""
        GAME_TITLES = ["洛克王国", "Roco", "roco", "Kingdom", "kingdom"]
        try:
            import ctypes
            import ctypes.wintypes

            EnumWindows = ctypes.windll.user32.EnumWindows
            GetForegroundWindow = ctypes.windll.user32.GetForegroundWindow
            GetWindowTextW = ctypes.windll.user32.GetWindowTextW
            IsWindowVisible = ctypes.windll.user32.IsWindowVisible
            GetClientRect = ctypes.windll.user32.GetClientRect
            ClientToScreen = ctypes.windll.user32.ClientToScreen

            EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)

            candidates = []

            def enum_cb(hwnd, _lparam):
                if not IsWindowVisible(hwnd):
                    return True
                buf = ctypes.create_unicode_buffer(256)
                GetWindowTextW(hwnd, buf, 256)
                title = buf.value
                if any(kw in title for kw in GAME_TITLES):
                    candidates.append((hwnd, title))
                return True

            EnumWindows(EnumWindowsProc(enum_cb), 0)
            if not candidates:
                return None

            fg_hwnd = int(GetForegroundWindow() or 0)
            found_hwnd = None
            found_title = ""
            if fg_hwnd:
                for hwnd, title in candidates:
                    if int(hwnd) == fg_hwnd:
                        found_hwnd, found_title = hwnd, title
                        break

            if found_hwnd is None:
                def _client_area(hwnd):
                    rect = ctypes.wintypes.RECT()
                    try:
                        GetClientRect(hwnd, ctypes.byref(rect))
                        return max(0, rect.right - rect.left) * max(0, rect.bottom - rect.top)
                    except Exception:
                        return 0

                found_hwnd, found_title = max(candidates, key=lambda item: _client_area(item[0]))

            rect = ctypes.wintypes.RECT()
            GetClientRect(found_hwnd, ctypes.byref(rect))
            client_w = rect.right - rect.left
            client_h = rect.bottom - rect.top
            if client_w <= 0 or client_h <= 0:
                return None

            pt = ctypes.wintypes.POINT(0, 0)
            ClientToScreen(found_hwnd, ctypes.byref(pt))
            return {
                "hwnd": int(found_hwnd),
                "title": str(found_title),
                "x": int(pt.x),
                "y": int(pt.y),
                "w": int(client_w),
                "h": int(client_h),
            }
        except Exception:
            return None

    def on_detect_game_window(self):
        """查找游戏窗口，自动计算窗口偏移和区域大小，适配窗口化模式。"""
        info = self._resolve_game_window_client_info()
        if not info:
            messagebox.showwarning(
                "未找到游戏窗口",
                "未检测到洛克王国游戏窗口。\n请确认游戏已启动，或手动输入分辨率后点击「应用」。"
            )
            return

        try:
            found_title = info["title"]
            client_w = int(info["w"])
            client_h = int(info["h"])
            offset_x = int(info["x"])
            offset_y = int(info["y"])
        except Exception as e:
            messagebox.showerror("检测失败", f"检测游戏窗口时出错：{e}")
            return

        if client_w <= 0 or client_h <= 0:
            messagebox.showerror("检测失败", f"游戏窗口「{found_title}」客户区大小异常：{client_w}x{client_h}")
            return

        # 保存窗口偏移到配置
        self.config_data["window_offset"] = {
            "x": offset_x, "y": offset_y,
            "w": client_w, "h": client_h,
        }
        self.config_data["window_client_size"] = {
            "w": client_w,
            "h": client_h,
        }

        res_str = f"{client_w}x{client_h}"
        self.resolution_var.set(res_str)
        self.apply_resolution_preset(res_str, show_message=False)
        self.save_ocr_capture_positions("detect_game_window")
        self._update_window_mode_label()

        messagebox.showinfo(
            "检测游戏窗口",
            f"找到窗口：{found_title}\n"
            f"客户区大小：{client_w}x{client_h}\n"
            f"屏幕偏移：({offset_x}, {offset_y})\n\n"
            f"已按客户区尺寸重新换算识别区域。"
        )

    def _refresh_game_window_runtime(self):
        """运行时刷新窗口位置，避免拖动后坐标失效。"""
        info = self._resolve_game_window_client_info()
        if not info:
            return False
        try:
            self.config_data["window_offset"] = {
                "x": int(info["x"]),
                "y": int(info["y"]),
                "w": int(info["w"]),
                "h": int(info["h"]),
            }
            self.config_data["window_client_size"] = {
                "w": int(info["w"]),
                "h": int(info["h"]),
            }
            return True
        except Exception:
            return False

    def save_ocr_capture_positions(self, note=""):
        """保存当前 OCR 截图位置，便于后续调试和对齐。"""
        try:
            cfg = self.config_data or {}
            payload = {
                "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "note": str(note or ""),
                "active_resolution": cfg.get("active_resolution", ""),
                "window_offset": cfg.get("window_offset", {}),
                "window_client_size": cfg.get("window_client_size", {}),
                "middle_region": cfg.get("middle_region", {}),
                "header_region": cfg.get("header_region", {}),
                "name_in_header": cfg.get("name_in_header", {}),
                "absolute_name_region": self.ocr.get_absolute_name_region(),
            }
            OCR_POSITION_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            return True
        except Exception:
            return False

    def apply_alpha(self, *_args):
        value = self._clamp_alpha(self.alpha_var.get())
        self.alpha_var.set(value)
        self.apply_background_opacity(value)
        self._debounced_save_config()

    def refresh_compact_species_list(self):
        if not self.compact_species_text:
            return
        unknown = clean_pet_name(self.config_data.get("unknown_species_name", "未识别"))
        display = {}
        for name, count in (self.species_total_counts or {}).items():
            cn = clean_pet_name(name)
            if not cn or cn == unknown:
                continue
            try:
                v = int(count)
            except Exception:
                continue
            if v <= 0:
                continue
            display[cn] = display.get(cn, 0) + v
        if not display and self.species_counts:
            for name, count in self.species_counts.items():
                cn = clean_pet_name(name)
                if not cn or cn == unknown:
                    continue
                try:
                    v = int(count)
                except Exception:
                    continue
                if v <= 0:
                    continue
                display[cn] = v
        lines = []
        if display:
            for name, count in sorted(display.items(), key=lambda x: (-int(x[1]), x[0])):
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
        try:
            self.root.update_idletasks()
        except Exception:
            pass

    def refresh_runtime_status(self):
        if self.running and self.paused:
            base = "已暂停"
        elif self.running:
            base = "运行中" if self.in_compact_mode else "正在运行"
        else:
            base = "未启动"
        if self.running and self.in_compact_mode:
            lock_text = "只读"
        else:
            lock_text = "已锁定" if self.window_locked else "可互动"
        self.runtime_state_var.set(f"{base}｜{lock_text}")
        self._update_lock_visual_state()

    def _clear_species_summary_core(self):
        """清空精灵分项累计（总表），保留每日总污染数与各日数字。"""
        for k in list((self.daily_species or {}).keys()):
            self.daily_species[k] = {}
        self.species_counts = {}
        self.species_total_counts = {}
        self.sync_today_from_memory(prefer_species_sum=False)
        self.species_total_counts = aggregate_species_totals(self.daily_species, self.species_counts)

    def confirm_clear_species_summary(self, *, parent=None, post_clear=None):
        has_totals = bool(self.species_total_counts)
        has_today = bool(self.species_counts)
        has_history = any(bool(v) for v in (self.daily_species or {}).values())
        if not has_totals and not has_today and not has_history:
            messagebox.showinfo("提示", "精灵统计总表已经是空的。", parent=parent or self.root)
            return False
        if not messagebox.askyesno(
            "清空精灵统计总表",
            "将清空所有「按精灵累计」的分项（含历史各天的精灵明细），\n"
            "「每日总污染数」里的天数与数字不会变。\n\n"
            "确定要清空吗？",
            parent=parent or self.root,
        ):
            return False
        self._clear_species_summary_core()
        self.save_data()
        self.update_display()
        self.status_var.set("已清空精灵统计总表")
        self.set_compact_hint("提示: 精灵总表已清空（每日总数未改）")
        if post_clear:
            post_clear()
        return True

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

    def confirm_archive_and_clear_today(self):
        self.sync_today_from_memory(True)
        if int(self.total_count) <= 0 and int(self.session_count) <= 0 and not self.species_counts:
            messagebox.showinfo("提示", "今天还没有计数，不用清空啦。")
            return False
        if not messagebox.askyesno(
            "清空并存档",
            "会把今天的统计先帮你留一份备份，\n"
            "然后把今天的数字全部归零，方便重新开始。\n\n"
            "以前其它日子的记录不会丢，只在「详情 → 历史记录」里能翻到这次备份。\n\n"
            "确定清空今天吗？",
        ):
            return False
        self.archive_and_clear_today_counts()
        return True

    def archive_and_clear_today_counts(self):
        day = today_str()
        self.sync_today_from_memory(True)
        archived_total = int(self.total_count)
        archived_species = dict(self.species_counts)
        archived_session = int(self.session_count)
        record = {
            "date": day,
            "archived_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "today_total": archived_total,
            "session_pollution_count": archived_session,
            "last_species": self.last_species_name,
            "species_counts": archived_species,
        }
        RECORD_DIR.mkdir(exist_ok=True)
        with open(TODAY_ARCHIVE_JSONL, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        csv_exists = TODAY_ARCHIVE_CSV.exists()
        with open(TODAY_ARCHIVE_CSV, "a", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            if not csv_exists:
                writer.writerow(
                    ["date", "archived_at", "today_total", "session_pollution_count", "last_species", "species_counts_json"]
                )
            writer.writerow(
                [
                    day,
                    record["archived_at"],
                    archived_total,
                    archived_session,
                    record["last_species"],
                    json.dumps(archived_species, ensure_ascii=False),
                ]
            )
        self.total_count = 0
        self.session_count = 0
        self.species_counts = {}
        self.daily_totals[day] = 0
        self.daily_species[day] = {}
        self.species_total_counts = aggregate_species_totals(self.daily_species, {})
        self.last_species_name = "无"
        self.sync_today_from_memory()
        self.save_data()
        self.status_var.set("已存档并清空今日数据")
        self.set_compact_hint("提示: 今日已写入存档并清零")
        self.update_display()

    def normalize_hotkey(self, value):
        return value.strip().lower().replace(" ", "")

    def _update_lock_visual_state(self):
        locked = bool(getattr(self, "window_locked", False))
        hotkey_fg = LOCK_ACTIVE_GREEN if locked else LOCK_IDLE_PURPLE
        runtime_fg = LOCK_ACTIVE_GREEN_SOFT if locked else LOCK_IDLE_LAVENDER
        status_fg = LOCK_ACTIVE_GREEN if locked else "#d7c5ff"
        for widget, color in (
            (getattr(self, "main_hotkey_detail_label", None), hotkey_fg),
            (getattr(self, "compact_hotkey_hint_label", None), hotkey_fg),
            (getattr(self, "runtime_status_label", None), runtime_fg),
            (getattr(self, "main_status_label", None), status_fg),
        ):
            try:
                if widget and widget.winfo_exists():
                    widget.configure(fg=color)
            except Exception:
                pass

    def refresh_hotkey_tip(self):
        hk = self.config_data["hotkeys"]
        self.tip_title_var.set("请用热键启动")
        self.tip_detail_var.set(
            f'启/关:{hk["start"]}  暂停:{hk["pause"]}  锁定/交互:{hk.get("lock", "-")}  +污:{hk["add"]}  -污:{hk["sub"]}'
        )
        self._update_lock_visual_state()

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
        """主线程刷新状态栏。仅对「相同文案」在 min_interval 内去重，避免与第二条全局节流冲突导致界面不更新。"""
        now = time.time()
        if not force:
            if text == self._last_status_push_text and (now - self._last_status_push_time) < min_interval:
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
        elif action == "lock":
            self._run_on_ui(self.toggle_window_lock)

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
                for action in ("add", "sub", "start", "pause", "lock"):
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
        try:
            self.hotkey_handles.append(
                keyboard.add_hotkey(
                    hk.get("lock", "-"),
                    lambda: self._trigger_hotkey_action("lock"),
                    suppress=False,
                    trigger_on_release=True,
                )
            )
            ok += 1
        except Exception as e:
            errors.append(f"锁定失败: {e}")

        if ok == 5:
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
            elif self.awaiting_hotkey == "lock":
                self.root.after(0, lambda: self.lock_key_var.set(hotkey))
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
        lock_key = self.normalize_hotkey(self.lock_key_var.get())

        keys = [add_key, sub_key, start_key, pause_key, lock_key]
        if any(not k for k in keys):
            messagebox.showerror("设置失败", "按键不能为空。")
            return
        if len(set(keys)) != len(keys):
            messagebox.showerror("设置失败", "五个按键不能重复。")
            return

        self.config_data["hotkeys"]["add"] = add_key
        self.config_data["hotkeys"]["sub"] = sub_key
        self.config_data["hotkeys"]["start"] = start_key
        self.config_data["hotkeys"]["pause"] = pause_key
        self.config_data["hotkeys"]["lock"] = lock_key
        self.register_hotkeys()
        self.save_config()
        self.status_var.set("热键已更新")


    def show_species_stats(self):
        top = tk.Toplevel(self.root)
        top.title("精灵污染统计")
        top.attributes("-topmost", True)
        top.geometry("920x620")
        top.minsize(820, 560)
        top.resizable(True, True)
        top.configure(bg="#171021")

        shell = tk.Frame(top, bg="#171021", highlightthickness=1, highlightbackground="#3b2f4c")
        shell.pack(fill="both", expand=True, padx=14, pady=14)

        header = tk.Frame(shell, bg="#171021")
        header.pack(fill="x", padx=16, pady=(14, 8))

        title_wrap = tk.Frame(header, bg="#171021")
        title_wrap.pack(side="left", fill="x", expand=True)

        tk.Label(
            title_wrap,
            text="污染统计详情",
            font=("Microsoft YaHei", 15, "bold"),
            fg="white",
            bg="#171021",
        ).pack(anchor="w")
        tk.Label(
            title_wrap,
            text="可直接编辑当前数据；历史记录只读浏览",
            font=UI_FONT_9,
            fg="#9f8cc9",
            bg="#171021",
        ).pack(anchor="w", pady=(4, 0))

        head_btns = tk.Frame(header, bg="#171021")
        head_btns.pack(side="right", anchor="n")

        tab_bar = tk.Frame(shell, bg="#171021")
        tab_bar.pack(fill="x", padx=16, pady=(0, 8))

        body = tk.Frame(shell, bg="#171021")
        body.pack(fill="both", expand=True, padx=16, pady=(0, 12))

        tab_font_active = ("Microsoft YaHei", 11, "bold")
        tab_font_idle = ("Microsoft YaHei", 11)
        tab_fg_active = "#a8d4ff"
        tab_fg_idle = "#7a6990"

        def make_panel(parent, title, subtitle=None):
            outer = tk.Frame(parent, bg="#221532", highlightthickness=1, highlightbackground="#4a3d5c")
            inner = tk.Frame(outer, bg="#221532")
            inner.pack(fill="both", expand=True, padx=12, pady=10)

            tk.Label(
                inner,
                text=title,
                font=("Microsoft YaHei", 11, "bold"),
                fg="white",
                bg="#221532",
            ).pack(anchor="w")
            if subtitle:
                tk.Label(
                    inner,
                    text=subtitle,
                    font=UI_FONT_8,
                    fg="#9f8cc9",
                    bg="#221532",
                ).pack(anchor="w", pady=(3, 8))
            return outer, inner

        current_wrap = tk.Frame(body, bg="#171021")
        current_wrap.grid_columnconfigure(0, weight=5, uniform="detail_cols")
        current_wrap.grid_columnconfigure(1, weight=3, uniform="detail_cols")
        current_wrap.grid_rowconfigure(0, weight=1)

        left_panel, left_inner = make_panel(current_wrap, "每日总污染数", "格式：YYYY-MM-DD: 数量")
        left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        right_panel, right_inner = make_panel(current_wrap, "精灵统计总表", "可直接编辑；右上可一键清空总表")
        right_panel.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

        left_text = tk.Text(
            left_inner,
            font=UI_FONT,
            bg="#26173a",
            fg="#f3e9ff",
            insertbackground="white",
            undo=True,
            relief=tk.FLAT,
            highlightthickness=1,
            highlightbackground="#4a3d5c",
            padx=10,
            pady=8,
            spacing1=2,
            spacing3=2,
        )
        left_text.pack(fill="both", expand=True)

        right_head = tk.Frame(right_inner, bg="#221532")
        right_head.pack(fill="x", pady=(0, 8))

        tk.Frame(right_head, bg="#221532").pack(side="left", expand=True, fill="x")

        right_text = tk.Text(
            right_inner,
            font=UI_FONT,
            bg="#26173a",
            fg="#f3e9ff",
            insertbackground="white",
            undo=True,
            relief=tk.FLAT,
            highlightthickness=1,
            highlightbackground="#4a3d5c",
            padx=10,
            pady=8,
            spacing1=2,
            spacing3=2,
        )
        right_text.pack(fill="both", expand=True)

        def refill_detail_species_text():
            right_text.delete("1.0", "end")
            if self.species_total_counts:
                for name, count in sorted(self.species_total_counts.items(), key=lambda x: (-int(x[1]), x[0])):
                    right_text.insert("end", f"{name}: {int(count)}\n")
            else:
                right_text.insert("end", "暂无记录\n")

        def detail_clear_species_summary():
            self.confirm_clear_species_summary(parent=top, post_clear=refill_detail_species_text)

        RoundedButton(
            right_head,
            text="清空总表",
            command=detail_clear_species_summary,
            bg_parent="#221532",
            font=UI_FONT_9,
            height=30,
        ).pack(side="right")

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

        archive_wrap = tk.Frame(body, bg="#171021")
        archive_panel, archive_inner = make_panel(
            archive_wrap,
            "历史记录",
            "只读浏览；每次在详情里执行“清空并存档”都会新增一条",
        )
        archive_panel.pack(fill="both", expand=True)

        archive_view = scrolledtext.ScrolledText(
            archive_inner,
            font=UI_FONT,
            bg="#26173a",
            fg="#e0d4ff",
            insertbackground="#e0d4ff",
            relief=tk.FLAT,
            highlightthickness=1,
            highlightbackground="#4a3d5c",
            wrap=tk.WORD,
            padx=10,
            pady=8,
            spacing1=2,
            spacing3=3,
        )
        archive_view.pack(fill="both", expand=True)

        def format_today_archive_for_detail():
            path = TODAY_ARCHIVE_JSONL
            head = f"源文件：{path.resolve()}\n{'─' * 44}\n\n"
            if not path.exists():
                return head + "暂无历史记录。\n"
            try:
                raw_lines = path.read_text(encoding="utf-8").splitlines()
            except Exception as e:
                return head + f"读取失败：{e}\n"
            rows = [ln.strip() for ln in raw_lines if ln.strip()]
            if not rows:
                return head + "存档文件为空。\n"
            blocks = []
            for ln in reversed(rows):
                try:
                    rec = json.loads(ln)
                except json.JSONDecodeError:
                    blocks.append("· 无法解析的行（已跳过）\n\n")
                    continue
                if not isinstance(rec, dict):
                    blocks.append("· 记录格式异常\n\n")
                    continue
                day = rec.get("date", "?")
                at = rec.get("archived_at", "?")
                try:
                    tot = int(rec.get("today_total", 0))
                except (TypeError, ValueError):
                    tot = 0
                try:
                    sess = int(rec.get("session_pollution_count", 0))
                except (TypeError, ValueError):
                    sess = 0
                last = rec.get("last_species", "无")
                sc = rec.get("species_counts") or {}
                if isinstance(sc, dict) and sc:
                    parts = []
                    for n, c in sc.items():
                        try:
                            parts.append((n, int(c)))
                        except (TypeError, ValueError):
                            parts.append((n, 0))
                    parts.sort(key=lambda x: (-x[1], x[0]))
                    lim = 48
                    sp = "、".join(f"{n}: {c}" for n, c in parts[:lim])
                    if len(parts) > lim:
                        sp += f" …（共 {len(parts)} 种）"
                else:
                    sp = "（无分项）"
                blocks.append(
                    f"日期：{day}    存档时间：{at}\n"
                    f"  当日总计：{tot}    本次计数：{sess}    最后精灵：{last}\n"
                    f"  分项：{sp}\n\n"
                )
            return head + "".join(blocks).rstrip() + "\n"

        def refresh_archive_view():
            archive_view.config(state="normal")
            archive_view.delete("1.0", "end")
            archive_view.insert("1.0", format_today_archive_for_detail())
            archive_view.config(state="disabled")

        tab_cur = tk.Label(tab_bar, text="当前数据", bg="#171021", cursor="hand2")
        tab_cur.pack(side="left")
        tk.Label(tab_bar, text=" · ", fg="#4a3d5c", bg="#171021").pack(side="left")
        tab_arc = tk.Label(tab_bar, text="历史记录", bg="#171021", cursor="hand2")
        tab_arc.pack(side="left")

        def select_tab(which):
            if which == "current":
                archive_wrap.pack_forget()
                current_wrap.pack(fill="both", expand=True)
                tab_cur.config(fg=tab_fg_active, font=tab_font_active)
                tab_arc.config(fg=tab_fg_idle, font=tab_font_idle)
            else:
                current_wrap.pack_forget()
                archive_wrap.pack(fill="both", expand=True)
                refresh_archive_view()
                tab_arc.config(fg=tab_fg_active, font=tab_font_active)
                tab_cur.config(fg=tab_fg_idle, font=tab_font_idle)

        tab_cur.bind("<Button-1>", lambda e: select_tab("current"))
        tab_arc.bind("<Button-1>", lambda e: select_tab("archive"))
        select_tab("current")

        bottom_bar = tk.Frame(shell, bg="#171021")
        bottom_bar.pack(fill="x", padx=16, pady=(0, 14))

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
                self.sync_today_from_memory(prefer_species_sum=False)
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

        def detail_clear_archive_and_refresh():
            if not self.confirm_archive_and_clear_today():
                return
            left_text.delete("1.0", "end")
            right_text.delete("1.0", "end")
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
            refresh_archive_view()

        RoundedButton(
            head_btns,
            text="清空并存档",
            command=detail_clear_archive_and_refresh,
            bg_parent="#171021",
            font=UI_FONT_9,
            height=32,
        ).pack(side="right", padx=(8, 0))
        RoundedButton(
            head_btns,
            text="保存",
            command=lambda: save_detail_edits(show_message=True),
            bg_parent="#171021",
            font=UI_FONT_9,
            height=32,
        ).pack(side="right")

        tk.Label(
            bottom_bar,
            text="关闭窗口会自动保存当前页可编辑内容",
            font=UI_FONT_8,
            fg="#8d79a8",
            bg="#171021",
        ).pack(side="left")

        top.protocol("WM_DELETE_WINDOW", on_detail_close)
        left_text.focus_set()
        self._schedule_window_round_corners(top)

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
        model_dir = self.model_dir_var.get().strip() or "paddleocr_models"
        self.config_data["paddleocr_model_dir"] = model_dir
        if self.running:
            return
        self.running = True
        self.paused = False
        self.confirm_hit_streak = 0
        self.last_detect_time = 0.0
        self.pause_tip_var.set("")
        self.status_var.set("启动中，OCR加载中...")
        self.set_compact_hint("提示: OCR加载中，请稍候")
        self.enter_compact_mode()
        self.set_window_lock(True)
        self.refresh_runtime_status()
        self.worker = threading.Thread(target=self._monitor_bootstrap, daemon=True)
        self.worker.start()
        self._apply_running_window_mode()

    def _start_ocr_warmup(self):
        if self._ocr_warmup_started or self.ocr.ready or self.ocr.loading:
            return
        self._ocr_warmup_started = True

        def _warm():
            try:
                self.ocr.ensure_loaded()
            finally:
                self._ocr_warmup_started = False

        self._ocr_warmup_thread = threading.Thread(target=_warm, daemon=True)
        self._ocr_warmup_thread.start()

    def _monitor_bootstrap(self):
        try:
            self._run_on_ui(self.status_var.set, "启动中，OCR加载中...")
            self._run_on_ui(self.set_compact_hint, "提示: OCR加载中，请稍候")
            while self.running and self.ocr.loading and not self.ocr.ready:
                time.sleep(0.1)
            if not self.running:
                return
            if not self.ocr.ready:
                if not self.ocr.ensure_loaded():
                    err = self.ocr.error or "PaddleOCR 不可用"
                    self._run_on_ui(self._monitor_start_failed, err)
                    return
            if not self.running:
                return
            self._run_on_ui(self._monitor_ready_ui)
            self.detect_loop()
        except Exception as e:
            self._run_on_ui(self._monitor_start_failed, str(e))

    def _monitor_ready_ui(self):
        self.status_var.set("监测中")
        self.set_compact_hint("")
        self.refresh_runtime_status()
        self.show_compact_timed_hint("遇到污染一定要打死或者捕捉哦", 60_000)

    def _monitor_start_failed(self, err_text):
        self.running = False
        self.paused = False
        self.window_locked = False
        self.set_clickthrough(False)
        self._cancel_clickthrough_guard()
        self.refresh_runtime_status()
        self.status_var.set("OCR未就绪")
        self.set_compact_hint("提示: OCR未就绪")
        messagebox.showerror("OCR未就绪", f"PaddleOCR 不可用。\n\n{err_text}")

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
        self.dismiss_compact_timed_hint()
        self.running = False
        self.paused = False
        self.pause_tip_var.set("")
        self.in_compact_mode = False
        self.window_locked = False
        self.set_clickthrough(False)
        self._cancel_clickthrough_guard()
        self.refresh_runtime_status()
        self.status_var.set("已停止")
        hk = self.config_data.get("hotkeys", {}) or {}
        sk = str(hk.get("start", "7")).upper()
        pk = str(hk.get("pause", "0")).upper()
        lk = str(hk.get("lock", "-")).upper()
        ak = str(hk.get("add", "8")).upper()
        uk = str(hk.get("sub", "9")).upper()
        self.set_compact_hint(f"提示: {sk} 启动/停止，{pk} 暂停，{lk} 锁定/交互，{ak} 加污染，{uk} 减污染")
        self._set_window_no_activate(False)
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
        """与 `roco_pollution_counter_v0.3_scan_07.py` 相同的监测循环（亮字预判 + 中间 OCR + 名称区 OCR）。"""
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
                    middle_gray = cv2.cvtColor(middle_frame, cv2.COLOR_BGRA2GRAY)

                    thumb = cv2.resize(
                        middle_gray, (0, 0), fx=0.25, fy=0.25, interpolation=cv2.INTER_AREA
                    )

                    adaptive_sleep = base_scan_interval

                    if prev_middle_thumb is not None and prev_middle_thumb.shape == thumb.shape:
                        diff = cv2.absdiff(thumb, prev_middle_thumb)
                        diff_mean = float(diff.mean())
                        if diff_mean < diff_threshold:
                            unchanged_loops += 1
                            if unchanged_loops < 4:
                                adaptive_sleep = base_scan_interval
                            elif unchanged_loops < 10:
                                adaptive_sleep = max(base_scan_interval, 1.0)
                            else:
                                adaptive_sleep = max(base_scan_interval, 1.6)
                        else:
                            unchanged_loops = 0
                            adaptive_sleep = base_scan_interval
                    else:
                        unchanged_loops = 0

                    prev_middle_thumb = thumb

                    blurred = cv2.GaussianBlur(middle_gray, (3, 3), 0)
                    _, binary = cv2.threshold(blurred, 185, 255, cv2.THRESH_BINARY)
                    white_pixels = int(cv2.countNonZero(binary))

                    if white_pixels >= 120:
                        bright_candidate_streak += 1
                    else:
                        bright_candidate_streak = 0

                    run_middle_ocr = False
                    if bright_candidate_streak >= 2:
                        run_middle_ocr = True

                    triggered = False
                    middle_text = ""

                    if run_middle_ocr:
                        middle_bgr = cv2.cvtColor(middle_frame, cv2.COLOR_BGRA2BGR)
                        all_middle_results = []
                        err_msg = ""

                        for scale, mode in [(3, "binary"), (3, "gray")]:
                            results, err = self.ocr.ocr_region(
                                image=middle_bgr,
                                region={
                                    "left": 0,
                                    "top": 0,
                                    "width": int(middle_bgr.shape[1]),
                                    "height": int(middle_bgr.shape[0]),
                                },
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
                            elif len(keyword) >= 2 and any(ch in t for ch in keyword) and float(item.get("confidence", 0.0)) >= 0.85:
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
                            self.set_status_async(f"识别出错: {err_msg[:24]}", min_interval=1.2)

                    now = time.time()

                    if triggered:
                        self.confirm_hit_streak += 1
                    else:
                        self.confirm_hit_streak = 0

                    if triggered and self.confirm_hit_streak >= confirm_frames and (now - self.last_detect_time) >= cooldown:
                        self.last_detect_time = now
                        self.confirm_hit_streak = 0
                        delay = float(self.config_data.get("name_read_delay", 0.0))
                        if delay > 0:
                            time.sleep(delay)

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
                                results, name_err = self.ocr.ocr_region(
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
                                self.set_status_async(f"名称识别出错: {err_msgs[0][:24]}", min_interval=1.2)

                        except Exception as name_ex:
                            self.set_status_async(f"名字识别失败: {str(name_ex)[:24]}", min_interval=1.2)

                        self._run_on_ui(self.count_detected_event, clean_name, clean_name, middle_text)

                except Exception as e:
                    self.set_status_async(f"错误: {str(e)[:40]}", min_interval=1.2)

                time.sleep(adaptive_sleep)

    def on_close(self):
        self._remove_mouse_passthrough_hook()
        self._cancel_clickthrough_guard()
        self._set_cursor_hidden(False)
        self.running = False
        self.in_compact_mode = False
        self._close_settings_dialog()
        self.save_data()
        self.save_config()
        self.unregister_hotkeys()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    if not ensure_run_as_administrator():
        sys.exit(0)
    App().run()
