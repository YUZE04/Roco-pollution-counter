"""检测线程：亮字预判 + 中间 OCR（关键字） + 名称 OCR（精灵名）。

从旧版 1.py 的 `App.detect_loop` 抽取而来，保留：
- 触发沿检测（关键字消失过一次才允许再次触发）
- 12 秒冷却（可配置但最少 12s）
- 白像素预判以节省 OCR 调用
- 自适应扫描间隔
"""

from __future__ import annotations

import ctypes
import sys
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

import cv2
import mss
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

from .utils import clean_pet_name, contains_keyword_fuzzy, normalize_text, pet_name_candidate_score


class DetectorThread(QThread):
    """后台检测线程。所有 UI 相关的状态都通过信号派发到主线程。"""

    # 一次有效的污染命中（species 为 "未识别" 时不计入总数）
    detected = pyqtSignal(str, str)  # (clean_name, middle_text)
    status_changed = pyqtSignal(str)
    ocr_error = pyqtSignal(str)
    ready_changed = pyqtSignal(bool)  # OCR 加载完成

    def __init__(self, ocr_reader, config_getter: Callable[[], Dict[str, Any]], parent=None):
        super().__init__(parent)
        self._ocr = ocr_reader
        self._get_cfg = config_getter
        self._stop_flag = False
        self._paused = False

    # ---------- 外部控制 ----------

    def request_stop(self) -> None:
        self._stop_flag = True

    def set_paused(self, paused: bool) -> None:
        self._paused = bool(paused)

    # ---------- 工具 ----------

    @staticmethod
    def _lower_thread_priority() -> None:
        try:
            if sys.platform == "win32":
                kernel32 = ctypes.windll.kernel32
                THREAD_PRIORITY_BELOW_NORMAL = -1
                kernel32.SetThreadPriority(
                    kernel32.GetCurrentThread(), THREAD_PRIORITY_BELOW_NORMAL
                )
        except Exception:
            pass

    # ---------- 主循环 ----------

    def run(self) -> None:  # noqa: C901 - 循环相对复杂但已拆小块
        self._lower_thread_priority()

        # 1) 先把 OCR 加载起来
        self.status_changed.emit("OCR 加载中…")
        try:
            ready = self._ocr.ensure_loaded()
        except Exception as e:
            self.ocr_error.emit(f"OCR 初始化异常：{e}")
            self.ready_changed.emit(False)
            return
        if not ready:
            self.ocr_error.emit(self._ocr.error or "PaddleOCR 未就绪")
            self.ready_changed.emit(False)
            return
        self.ready_changed.emit(True)
        self.status_changed.emit("监测中")

        cfg = self._get_cfg()
        cooldown = max(12.0, float(cfg.get("cooldown_seconds", 12.0)))
        base_scan_interval = float(cfg.get("scan_interval", 0.70))
        confirm_frames = int(cfg.get("confirm_frames", 1))

        last_detect_time = 0.0
        confirm_hit_streak = 0
        trigger_armed = True
        miss_frames_to_rearm = 3
        consecutive_miss = 0
        bright_candidate_streak = 0

        with mss.mss() as sct:
            last_paused_state = False
            while not self._stop_flag:
                try:
                    if self._paused:
                        if not last_paused_state:
                            self.status_changed.emit("已暂停")
                            last_paused_state = True
                        time.sleep(max(base_scan_interval, 0.7))
                        continue
                    if last_paused_state:
                        self.status_changed.emit("监测中")
                        last_paused_state = False

                    cfg = self._get_cfg()
                    middle_region = dict(cfg["middle_region"])
                    bright_threshold = max(80, min(245, int(cfg.get("middle_bright_threshold", 170))))
                    white_pixels_threshold = max(1, int(cfg.get("middle_white_pixels_threshold", 45)))
                    bright_streak_required = max(0, int(cfg.get("middle_bright_streak_required", 1)))
                    partial_conf_threshold = max(
                        0.0, min(1.0, float(cfg.get("middle_partial_confidence_threshold", 0.45)))
                    )
                    min_char_match_ratio = max(
                        0.0, min(1.0, float(cfg.get("middle_min_char_match_ratio", 0.5)))
                    )

                    middle_frame = np.array(sct.grab(middle_region))
                    middle_gray = cv2.cvtColor(middle_frame, cv2.COLOR_BGRA2GRAY)

                    blurred = cv2.GaussianBlur(middle_gray, (3, 3), 0)
                    _, binary = cv2.threshold(blurred, bright_threshold, 255, cv2.THRESH_BINARY)
                    white_pixels = int(cv2.countNonZero(binary))

                    if white_pixels >= white_pixels_threshold:
                        bright_candidate_streak += 1
                    else:
                        bright_candidate_streak = max(0, bright_candidate_streak - 1)

                    run_middle_ocr = (
                        bright_streak_required <= 0
                        or white_pixels >= white_pixels_threshold
                        or bright_candidate_streak >= bright_streak_required
                    )

                    triggered = False
                    middle_text = ""

                    if run_middle_ocr:
                        middle_bgr = cv2.cvtColor(middle_frame, cv2.COLOR_BGRA2BGR)
                        triggered, middle_text = self._middle_ocr_trigger(
                            cfg, middle_bgr, partial_conf_threshold, min_char_match_ratio
                        )

                    now = time.time()

                    if triggered:
                        confirm_hit_streak += 1
                        consecutive_miss = 0
                    else:
                        confirm_hit_streak = 0
                        consecutive_miss += 1
                        if consecutive_miss >= miss_frames_to_rearm:
                            trigger_armed = True

                    if (
                        triggered
                        and trigger_armed
                        and confirm_hit_streak >= confirm_frames
                        and (now - last_detect_time) >= cooldown
                    ):
                        last_detect_time = now
                        confirm_hit_streak = 0
                        trigger_armed = False

                        delay = float(cfg.get("name_read_delay", 0.0))
                        if delay > 0:
                            time.sleep(delay)

                        clean_name = self._read_species_name(sct, cfg) or cfg.get(
                            "unknown_species_name", "未识别"
                        )
                        self.detected.emit(clean_name, middle_text)

                except Exception as e:
                    self.ocr_error.emit(f"检测异常：{e}")

                time.sleep(base_scan_interval)

        self.status_changed.emit("已停止")

    # ---------- OCR 子步骤 ----------

    def _middle_ocr_trigger(
        self,
        cfg: Dict[str, Any],
        middle_bgr: np.ndarray,
        partial_conf_threshold: float,
        min_char_match_ratio: float,
    ) -> Tuple[bool, str]:
        mode_list = cfg.get("middle_ocr_modes", [[3, "binary"], [3, "gray"], [4, "binary"]])
        local_region = {
            "left": 0,
            "top": 0,
            "width": int(middle_bgr.shape[1]),
            "height": int(middle_bgr.shape[0]),
        }

        all_results: List[dict] = []
        for item in mode_list:
            if not isinstance(item, (list, tuple)) or len(item) != 2:
                continue
            scale, mode = item
            results, err = self._ocr.ocr_region(
                image=middle_bgr,
                region=local_region,
                scale=scale,
                preprocess_mode=mode,
            )
            if err:
                continue
            all_results.extend(results)

        keyword = normalize_text(cfg.get("middle_keyword", "力量"))
        fallback_keywords = [normalize_text(x) for x in cfg.get("middle_fallback_keywords", ["力量"])]

        triggered = False
        best_text = ""
        best_conf = 0.0
        for item in all_results:
            t = normalize_text(item.get("text", ""))
            confidence = float(item.get("confidence", 0.0))
            if not t:
                continue
            matched_chars = sum(1 for ch in keyword if ch in t) if keyword else 0
            char_match_ratio = matched_chars / max(len(keyword), 1) if keyword else 0.0
            if keyword and contains_keyword_fuzzy(t, keyword):
                pass
            elif keyword and char_match_ratio >= min_char_match_ratio and confidence >= partial_conf_threshold:
                pass
            elif any(k and k in t for k in fallback_keywords):
                pass
            else:
                continue
            triggered = True
            if confidence >= best_conf:
                best_text = t
                best_conf = confidence
        return triggered, (best_text or keyword or "力量")

    def _read_species_name(self, sct, cfg: Dict[str, Any]) -> Optional[str]:
        try:
            abs_region = self._ocr.get_absolute_name_region()
            frame = np.array(sct.grab(abs_region))
            name_bgr = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
            local_region = {
                "left": 0,
                "top": 0,
                "width": int(name_bgr.shape[1]),
                "height": int(name_bgr.shape[0]),
            }
            mode_list = cfg.get("header_ocr_modes", [[4, "binary"], [3, "gray"]])
            all_results: List[dict] = []
            for item in mode_list:
                if not isinstance(item, (list, tuple)) or len(item) != 2:
                    continue
                scale, mode = item
                results, err = self._ocr.ocr_region(
                    image=name_bgr,
                    region=local_region,
                    scale=scale,
                    preprocess_mode=mode,
                )
                if err:
                    continue
                for it in results:
                    cleaned = clean_pet_name(it.get("text", ""))
                    if cleaned and cleaned != "未识别":
                        all_results.append({
                            "clean": cleaned,
                            "confidence": float(it.get("confidence", 0.0)),
                            "score": pet_name_candidate_score(
                                it.get("text", ""), float(it.get("confidence", 0.0))
                            ),
                        })
            if not all_results:
                return None
            merged: Dict[str, Dict[str, Any]] = {}
            for item in all_results:
                key = item["clean"]
                slot = merged.setdefault(key, {"count": 0, "best_conf": 0.0, "best_score": -999.0})
                slot["count"] += 1
                slot["best_conf"] = max(slot["best_conf"], item["confidence"])
                slot["best_score"] = max(slot["best_score"], item["score"])
            ranked = sorted(
                merged.items(),
                key=lambda kv: (kv[1]["count"], kv[1]["best_score"], kv[1]["best_conf"], len(kv[0])),
                reverse=True,
            )
            return ranked[0][0]
        except Exception as e:
            self.ocr_error.emit(f"名字识别失败：{e}")
            return None
