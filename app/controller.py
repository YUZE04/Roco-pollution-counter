"""应用控制器：把 UI 和后端线程连起来。"""

from __future__ import annotations

import sys
from typing import Any, Dict

from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtWidgets import QApplication, QMessageBox

from .backend import config as cfg_mod
from .backend.data import PollutionData
from .backend.detector import DetectorThread
from .backend.hotkeys import HotkeyThread
from .backend.ocr import LocalPaddleOCRReader
from .backend.utils import clean_pet_name


class AppController(QObject):
    """控制器：拥有配置/数据/线程，响应 UI 请求。"""

    # 转发到 UI 的信号
    data_changed = pyqtSignal()
    status_text_changed = pyqtSignal(str)
    running_changed = pyqtSignal(bool)
    paused_changed = pyqtSignal(bool)
    locked_changed = pyqtSignal(bool)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._config: Dict[str, Any] = cfg_mod.load_config()
        self._data = PollutionData(self)

        # OCR 只构造，不预加载
        self._ocr = LocalPaddleOCRReader(config_getter=lambda: self._config)

        # 热键线程：常驻
        self._hotkeys = HotkeyThread(hotkeys_getter=lambda: self._config.get("hotkeys", {}))
        self._hotkeys.hotkey_triggered.connect(self._on_hotkey)
        self._hotkeys.start()

        # 检测线程：按需启动
        self._detector: DetectorThread | None = None
        self._running = False
        self._paused = False
        self._locked = bool(self._config.get("overlay_locked", False))

        # 定期节流保存配置
        self._cfg_save_timer = QTimer(self)
        self._cfg_save_timer.setSingleShot(True)
        self._cfg_save_timer.timeout.connect(self._flush_config)
        self._cfg_dirty = False

    # ---------- 属性 ----------

    @property
    def config(self) -> Dict[str, Any]:
        return self._config

    @property
    def data(self) -> PollutionData:
        return self._data

    @property
    def running(self) -> bool:
        return self._running

    @property
    def paused(self) -> bool:
        return self._paused

    @property
    def locked(self) -> bool:
        return self._locked

    # ---------- 配置 ----------

    def mark_config_dirty(self) -> None:
        self._cfg_dirty = True
        if not self._cfg_save_timer.isActive():
            self._cfg_save_timer.start(1500)

    def _flush_config(self) -> None:
        if self._cfg_dirty:
            cfg_mod.save_config(self._config)
            self._cfg_dirty = False

    # ---------- 监测 ----------

    def toggle_monitor(self) -> None:
        if self._running:
            self.stop_monitor()
        else:
            self.start_monitor()

    def start_monitor(self) -> None:
        if self._running:
            return
        self._running = True
        self._paused = False
        self._detector = DetectorThread(self._ocr, config_getter=lambda: self._config, parent=self)
        self._detector.detected.connect(self._on_species_detected)
        self._detector.status_changed.connect(self._on_status_text)
        self._detector.ocr_error.connect(self._on_ocr_error)
        self._detector.ready_changed.connect(self._on_ocr_ready)
        self._detector.finished.connect(self._on_detector_finished)
        self._detector.start()
        self.running_changed.emit(True)

    def stop_monitor(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._detector is not None:
            self._detector.request_stop()
            # 不阻塞，finished 会触发清理
        self.running_changed.emit(False)

    def toggle_pause(self) -> None:
        if not self._running:
            return
        self._paused = not self._paused
        if self._detector is not None:
            self._detector.set_paused(self._paused)
        self.paused_changed.emit(self._paused)

    # ---------- 锁定 ----------

    def toggle_lock(self) -> None:
        self._locked = not self._locked
        self._config["overlay_locked"] = self._locked
        self.mark_config_dirty()
        self.locked_changed.emit(self._locked)

    def set_locked(self, locked: bool) -> None:
        if self._locked == bool(locked):
            return
        self._locked = bool(locked)
        self._config["overlay_locked"] = self._locked
        self.mark_config_dirty()
        self.locked_changed.emit(self._locked)

    # ---------- 数据操作 ----------

    def manual_add(self) -> None:
        if self._data.manual_add():
            self.data_changed.emit()
        else:
            self.status_text_changed.emit("没有上一只精灵，无法手动加")

    def reset_today(self) -> None:
        self._data.reset_today()
        self.data_changed.emit()
        self.status_text_changed.emit("今日统计已清空")

    def manual_sub(self) -> None:
        if self._data.manual_sub():
            self.data_changed.emit()
        else:
            self.status_text_changed.emit("没有可减的数量")

    # ---- 统计修改（由"编辑统计"对话框调用）----

    def set_today_species(self, name: str, value: int) -> None:
        self._data.set_today_species_count(name, int(value))
        self.data_changed.emit()
        self.status_text_changed.emit(f"已修改今日 [{name}] = {int(value)}")

    def set_species_total(self, name: str, value: int) -> None:
        self._data.set_species_total_count(name, int(value))
        self.data_changed.emit()
        self.status_text_changed.emit(f"已修改累计 [{name}] = {int(value)}")

    def set_daily_total(self, day: str, value: int) -> None:
        self._data.set_daily_total(day, int(value))
        self.data_changed.emit()
        self.status_text_changed.emit(f"已修改 {day} 总数 = {int(value)}")

    def delete_today_species(self, name: str) -> None:
        self._data.set_today_species_count(name, 0)
        self.data_changed.emit()
        self.status_text_changed.emit(f"已删除今日 [{name}]")

    def delete_species_total(self, name: str) -> None:
        self._data.set_species_total_count(name, 0)
        self.data_changed.emit()
        self.status_text_changed.emit(f"已删除累计 [{name}]")

    # ---- 识别游戏窗口 ----

    def detect_game_window(self) -> dict | None:
        """检测游戏窗口并把结果写入配置。返回窗口信息或 None。"""
        from .backend.window_detect import find_game_window, apply_game_window
        info = find_game_window()
        if not info:
            self.status_text_changed.emit("未检测到游戏窗口")
            return None
        mode = apply_game_window(self._config, info)
        self.mark_config_dirty()
        self.status_text_changed.emit(
            f"已识别：{info['title']}  {info['w']}x{info['h']}  偏移({info['x']},{info['y']})  [{mode}]"
        )
        return info

    # ---------- 槽 ----------

    # OCR 误识别为这些字符时一律忽略（不计入总数）
    _IGNORED_NAMES = {"无", "无字", "无 ", " 无"}

    def _on_species_detected(self, clean_name: str, middle_text: str) -> None:
        name = clean_pet_name(clean_name)
        unknown = self._config.get("unknown_species_name", "未识别")
        if name == unknown:
            self.status_text_changed.emit(f"命中但未识别: {middle_text[:18]}")
            return
        # "无" 这类无意义识别结果直接丢弃，不增加总数
        if name.strip() in self._IGNORED_NAMES:
            self.status_text_changed.emit(f"忽略噪声识别：{name}")
            return
        self._data.increment(name)
        self.data_changed.emit()
        self.status_text_changed.emit(f"+1 {name}")

    def _on_status_text(self, text: str) -> None:
        self.status_text_changed.emit(text)

    def _on_ocr_error(self, text: str) -> None:
        self.status_text_changed.emit(f"错误: {text[:60]}")

    def _on_ocr_ready(self, ready: bool) -> None:
        if ready:
            self.status_text_changed.emit("OCR 已就绪，开始监测")
        else:
            self.status_text_changed.emit("OCR 加载失败")
            # 加载失败，终止
            self._running = False
            self.running_changed.emit(False)

    def _on_detector_finished(self) -> None:
        self._detector = None

    def _on_hotkey(self, action: str) -> None:
        if action == "add":
            self.manual_add()
        elif action == "sub":
            self.manual_sub()
        elif action == "start":
            self.toggle_monitor()
        elif action == "pause":
            self.toggle_pause()
        elif action == "lock":
            self.toggle_lock()

    # ---------- 退出 ----------

    def shutdown(self) -> None:
        self.stop_monitor()
        self._hotkeys.request_stop()
        self._hotkeys.wait(500)
        if self._detector is not None:
            self._detector.wait(2000)
        self._data.save(force=True)
        self._flush_config()
