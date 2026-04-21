"""应用控制器：把 UI 和后端线程连起来。"""

from __future__ import annotations

import sys
import time
from typing import Any, Dict

from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtWidgets import QApplication, QInputDialog, QMessageBox

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
    show_main_requested = pyqtSignal()

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._config: Dict[str, Any] = cfg_mod.load_config()
        self._data = PollutionData(self)

        # OCR 只构造，不预加载
        try:
            self._ocr = LocalPaddleOCRReader(config_getter=lambda: self._config)
        except Exception as e:
            raise RuntimeError(f"OCR 初始化失败：{e}") from e

        # 热键线程：常驻
        try:
            self._hotkeys = HotkeyThread(hotkeys_getter=lambda: self._config.get("hotkeys", {}))
            self._hotkeys.hotkey_triggered.connect(self._on_hotkey)
            self._hotkeys.start()
        except Exception as e:
            raise RuntimeError(f"热键线程启动失败：{e}") from e

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

        # 自动计数硬冷却：两次自动 +1 之间的最小时间间隔（秒）。
        # 不论 detector 怎么报、热键 hotkey 怎么按，都拦在这里。手动 +/- 不受影响。
        self._last_auto_increment_ts: float = 0.0

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
        self.paused_changed.emit(False)

    def stop_monitor(self) -> None:
        if not self._running:
            return
        self._running = False
        self._paused = False
        if self._detector is not None:
            self._detector.request_stop()
            # 不阻塞，finished 会触发清理
        self.running_changed.emit(False)
        self.paused_changed.emit(False)

    def toggle_pause(self) -> None:
        if not self._running:
            return
        self._paused = not self._paused
        if self._detector is not None:
            self._detector.set_paused(self._paused)
        self.status_text_changed.emit("已暂停" if self._paused else "监测中")
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
        # 先试默认回退：last_species → 今日榜首 → 累计榜首
        if self._data.manual_add():
            self.data_changed.emit()
            return
        # 没有任何精灵信息：弹输入框让用户临时指定一个
        name = self._prompt_species_name("手动 +1：请输入精灵名字")
        if not name:
            self.status_text_changed.emit("已取消手动加")
            return
        if self._data.manual_add(species=name):
            self.data_changed.emit()
        else:
            self.status_text_changed.emit("无法识别该名字")

    def reset_today(self) -> None:
        self._data.reset_today()
        self.data_changed.emit()
        self.status_text_changed.emit("今日明细已清空")

    def import_count_file(self, file_path: str) -> tuple[bool, str]:
        try:
            if self._running:
                self.stop_monitor()
            result = self._data.replace_from_file(file_path)
        except Exception as e:
            return False, f"导入失败：{e}"

        self.data_changed.emit()
        self.status_text_changed.emit("已导入旧版统计（累计模式）")

        summary = (
            f"已导入：{result['source_path']}\n"
            f"总污染数：{result['count']}\n"
            f"累计精灵条目：{result['species_total']}\n"
            "导入方式：累计模式（不按天拆分）"
        )
        if result.get("backup_path"):
            summary += f"\n已备份当前数据到：{result['backup_path']}"
        return True, summary

    def manual_sub(self) -> None:
        if self._data.manual_sub():
            self.data_changed.emit()
            return
        # 回退失败：弹输入框指定
        name = self._prompt_species_name("手动 -1：请输入精灵名字")
        if not name:
            self.status_text_changed.emit("已取消手动减")
            return
        if self._data.manual_sub(species=name):
            self.data_changed.emit()
        else:
            self.status_text_changed.emit(f"「{name}」没有可减的数量")

    def _prompt_species_name(self, prompt: str) -> str:
        """弹输入框让用户输入精灵名。带历史下拉候选。返回空串表示取消。"""
        # 候选：今日 + 累计里出现过的精灵
        candidates: list[str] = []
        for src in (self._data.species_counts, self._data.species_total_counts):
            for k in src.keys():
                if k and k not in candidates:
                    candidates.append(k)
        default = candidates[0] if candidates else ""
        try:
            if candidates:
                text, ok = QInputDialog.getItem(
                    None, "污染计数器", prompt, candidates, 0, True
                )
            else:
                text, ok = QInputDialog.getText(
                    None, "污染计数器", prompt, text=default
                )
        except Exception:
            return ""
        if not ok:
            return ""
        return (text or "").strip()

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

    def archive_and_clear_species(self, name: str) -> tuple[bool, str]:
        try:
            record = self._data.archive_and_clear_species(name)
        except Exception as e:
            return False, str(e)

        self.data_changed.emit()
        self.status_text_changed.emit(f"已存档并清空 [{record['species']}]")
        message = (
            f"已存档：{record['species']}\n"
            f"累计次数：{record['species_total_count']}\n"
            f"今日次数：{record['today_species_count']}\n"
            f"移出当前累计：{record['removed_from_current_total']}\n"
            f"存档时间：{record['archived_at']}"
        )
        return True, message

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

    # 自动计数最小间隔（秒）。比 detector cooldown 更宽松一档，
    # 主要兜底防止 detector 上层 bug / OCR 极端抖动导致的同场重复。
    _AUTO_INCREMENT_MIN_INTERVAL = 10.0

    def _on_species_detected(self, clean_name: str, middle_text: str) -> None:
        name = clean_pet_name(clean_name)
        # 应用用户/默认别名表修正 OCR 常见误识别
        name = self._apply_name_alias(name)
        unknown = self._config.get("unknown_species_name", "未识别")
        if name == unknown:
            self.status_text_changed.emit(f"命中但未识别: {middle_text[:18]}")
            return
        # "无" 这类无意义识别结果直接丢弃，不增加总数
        if name.strip() in self._IGNORED_NAMES:
            self.status_text_changed.emit(f"忽略噪声识别：{name}")
            return
        # 硬门槛：两次自动 +1 之间至少 _AUTO_INCREMENT_MIN_INTERVAL 秒
        now = time.time()
        gap = now - self._last_auto_increment_ts
        if gap < self._AUTO_INCREMENT_MIN_INTERVAL:
            remain = self._AUTO_INCREMENT_MIN_INTERVAL - gap
            self.status_text_changed.emit(
                f"忽略：距上次自动计数仅 {gap:.1f}s（需 ≥ {self._AUTO_INCREMENT_MIN_INTERVAL:.0f}s，剩 {remain:.1f}s）"
            )
            return
        self._last_auto_increment_ts = now
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

    def _apply_name_alias(self, name: str) -> str:
        """根据 config.ocr_name_aliases 把 OCR 常见误识别映射到真实名字。"""
        if not name:
            return name
        aliases = self._config.get("ocr_name_aliases") or {}
        if not isinstance(aliases, dict):
            return name
        mapped = aliases.get(name)
        if isinstance(mapped, str) and mapped.strip():
            return mapped.strip()
        return name

    def _on_hotkey(self, action: str) -> None:
        if action == "add":
            self.manual_add()
        elif action == "sub":
            self.manual_sub()
        elif action in ("start", "pause"):
            # 两个动作现在都只做暂停/继续；"开始监测"请走主窗口按钮或悬浮窗右键菜单。
            if self._running:
                self.toggle_pause()
            else:
                self.status_text_changed.emit("请先在主窗口点击「开始监测」")
        elif action == "lock":
            self.toggle_lock()
        elif action == "show_main":
            self.show_main_requested.emit()

    # ---------- 退出 ----------

    def shutdown(self) -> None:
        self.stop_monitor()
        self._hotkeys.request_stop()
        self._hotkeys.wait(500)
        if self._detector is not None:
            self._detector.wait(2000)
        self._data.save(force=True)
        self._flush_config()
