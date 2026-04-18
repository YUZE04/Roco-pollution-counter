"""主配置/统计窗口。"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
import webbrowser
from typing import Dict, List, Optional, Tuple

from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QKeySequence
from PyQt6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import theme
from .. import APP_VERSION
from .components import Card, IconButton, Pill, SectionHeader, StatTile
from .delegates import CountBarDelegate, SparkLine
from .edit_dialogs import edit_count_dialog, edit_daily_dialog
from .icons import get_icon, icon_size
from .motion import animate_tab_switch, count_up, slide_in
from .title_bar import TitleBar
from .toast import ToastManager

try:
    # 运行期引用类型，避免循环依赖
    from ..controller import AppController  # noqa: F401
except Exception:
    AppController = None  # type: ignore


HOTKEY_ACTIONS = [
    ("start", "启/停监测"),
    ("pause", "暂停/继续"),
    ("add", "+污（手动）"),
    ("sub", "-污（手动）"),
    ("lock", "锁定/解锁悬浮窗"),
]

BUILTIN_RESOLUTIONS = ["1280x720", "1920x1080", "2560x1440", "2560x1600_150缩放", "3840x2160"]


class UpdateCheckWorker(QThread):
    """后台检查更新。完成后发出信号给 UI。"""

    finished_with_result = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self._url = url

    def run(self) -> None:
        try:
            req = urllib.request.Request(
                self._url,
                headers={"User-Agent": "Roco-pollution-counter"},
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            self.finished_with_result.emit(data)
        except urllib.error.URLError as e:
            self.failed.emit(f"网络错误：{e}")
        except Exception as e:
            self.failed.emit(f"{e}")


class MainWindow(QMainWindow):
    """主配置/统计窗。"""

    # 向控制器/Application 发出的意图信号
    toggle_monitor_requested = pyqtSignal()
    show_overlay_requested = pyqtSignal()
    quit_requested = pyqtSignal()
    reset_today_requested = pyqtSignal()
    hotkeys_changed = pyqtSignal()

    def __init__(self, controller=None):
        super().__init__()
        # 无边框 + 自定义深紫标题栏，放弃 Mica/Acrylic 材质。
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowMinMaxButtonsHint
        )

        self._controller = controller
        self._suppress_item_changed = False
        self.setWindowTitle(f"污染计数器 {APP_VERSION}")
        self.resize(720, 600)
        # 纯色深紫背景（稳定版）
        self.setStyleSheet(
            theme.qss_main_window()
            + f"\nQMainWindow, #CentralWidget {{ background-color: {theme.BG_DEEP}; }}"
        )

        central = QWidget(objectName="CentralWidget")
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # 自定义标题栏
        self.title_bar = TitleBar(self, title=f"污染计数器  {APP_VERSION}")
        outer.addWidget(self.title_bar)

        # 内容区
        content = QWidget()
        outer.addWidget(content, 1)
        root = QVBoxLayout(content)
        root.setContentsMargins(12, 12, 12, 12)

        # 顶部：徽章 + 状态文字（标题已经在窗口标题栏里，不再重复）
        status_bar = QHBoxLayout()
        status_bar.setSpacing(10)
        status_bar.setContentsMargins(2, 2, 2, 2)
        self.lbl_state_pill = Pill("未启动", color=theme.FG_DIM)
        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet(
            f"color:{theme.FG_DIM};background:transparent;"
        )
        status_bar.addWidget(self.lbl_state_pill)
        status_bar.addWidget(self.lbl_status, 1)

        # 操作按钮靠右，和状态共用一排，节省空间
        self.btn_toggle_monitor = IconButton("开始监测", icon="play", primary=True)
        self.btn_show_overlay = IconButton("悬浮窗", icon="window")
        self.btn_refresh_stats = IconButton("刷新", icon="refresh")
        self.btn_quit = IconButton("退出", icon="power")
        status_bar.addWidget(self.btn_toggle_monitor)
        status_bar.addWidget(self.btn_show_overlay)
        status_bar.addWidget(self.btn_refresh_stats)
        status_bar.addWidget(self.btn_quit)
        root.addLayout(status_bar)

        self.btn_toggle_monitor.clicked.connect(self.toggle_monitor_requested.emit)
        self.btn_show_overlay.clicked.connect(self.show_overlay_requested.emit)
        self.btn_refresh_stats.clicked.connect(self._refresh_stats_tab)
        self.btn_quit.clicked.connect(self.quit_requested.emit)

        # 选项卡
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_status_tab(), "状态")
        self.tabs.addTab(self._build_settings_tab(), "设置")
        self.tabs.addTab(self._build_stats_tab(), "统计")
        self.tabs.addTab(self._build_about_tab(), "关于")
        self.tabs.currentChanged.connect(self._on_tab_changed)
        root.addWidget(self.tabs, 1)

        # Toast 管理器（右下角通知）
        self._toasts = ToastManager(self)

        # 初始填充
        if self._controller is not None:
            self._load_from_config()
            self._refresh_stats_tab()

    # ================================================================
    # 公共接口
    # ================================================================

    def set_controller(self, controller) -> None:
        self._controller = controller
        self._load_from_config()
        self._refresh_stats_tab()

    def _on_tab_changed(self, index: int) -> None:
        w = self.tabs.widget(index)
        if w is not None:
            animate_tab_switch(w, duration=240, dx=12)

    def showEvent(self, event):  # noqa: D401
        super().showEvent(event)
        # 首次显示时给当前 tab 内容一个轻量滑入动画
        if not getattr(self, "_intro_played", False):
            self._intro_played = True
            try:
                cur = self.tabs.currentWidget()
                if cur is not None:
                    animate_tab_switch(cur, duration=240, dx=10)
            except Exception:
                pass

    def set_monitor_button_text(self, running: bool) -> None:
        if running:
            self.btn_toggle_monitor.setText("停止监测")
            self.btn_toggle_monitor.set_icon_name("stop")
            self.lbl_state_pill.set_state("监测中", theme.FG_SUCCESS)
        else:
            self.btn_toggle_monitor.setText("开始监测")
            self.btn_toggle_monitor.set_icon_name("play")
            self.lbl_state_pill.set_state("未启动", theme.FG_DIM)

    def set_status_text(self, text: str) -> None:
        self.lbl_status.setText(text)
        # 临时消息同时弹 toast（持久性状态如"监测中"/"未启动"不弹）
        if not text:
            return
        t = text.strip()
        persistent_prefixes = ("监测中", "未启动", "正在加载", "OCR 已就绪")
        if any(t.startswith(p) for p in persistent_prefixes):
            return
        # 选合适的图标
        if t.startswith("+1"):
            icon = "sparkle"
        elif t.startswith("错误"):
            icon = "info"
        elif "已修改" in t or "已删除" in t or "已清空" in t:
            icon = "refresh"
        elif "已识别" in t:
            icon = "eye"
        else:
            icon = "info"
        if hasattr(self, "_toasts"):
            self._toasts.show(t[:80], icon=icon)

    # ================================================================
    # 状态 tab
    # ================================================================

    def _build_status_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(4, 4, 4, 4)
        v.setSpacing(theme.SPACE_MD)

        # 两张指标卡：今日总数 + 最近精灵
        tiles_row = QHBoxLayout()
        tiles_row.setSpacing(theme.SPACE_MD)
        self.tile_today_total = StatTile(
            "今日总污染数", "0", icon="sparkle", accent=theme.FG_COUNT
        )
        self.tile_last_species = StatTile(
            "最近精灵", "无", icon="eye", accent=theme.FG_SPECIES
        )
        # 最近精灵是文字，字体略小一些
        self.tile_last_species.lbl_value.setStyleSheet(
            f"color:{theme.FG_SPECIES};font-size:17pt;font-weight:700;"
            f"background:transparent;letter-spacing:-0.5px;"
        )
        tiles_row.addWidget(self.tile_today_total, 1)
        tiles_row.addWidget(self.tile_last_species, 1)
        v.addLayout(tiles_row)

        # 兼容字段：外部逻辑仍可读 self.lbl_today_total / self.lbl_last_species
        self.lbl_today_total = self.tile_today_total.lbl_value
        self.lbl_last_species = self.tile_last_species.lbl_value

        # 精灵明细卡
        card = Card(padding=14)
        card.body().addWidget(
            SectionHeader("今日精灵明细", icon="chart", subtitle="按今日出现次数排序")
        )
        self.tbl_today_species = QTableWidget(0, 2)
        self.tbl_today_species.setHorizontalHeaderLabels(["精灵", "今日次数"])
        self.tbl_today_species.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.tbl_today_species.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        self.tbl_today_species.verticalHeader().setVisible(False)
        self.tbl_today_species.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tbl_today_species.setAlternatingRowColors(True)
        self.tbl_today_species.cellDoubleClicked.connect(self._on_edit_today_row)
        self.tbl_today_species.verticalHeader().setDefaultSectionSize(32)
        self._delegate_today = CountBarDelegate(value_column=1)
        self.tbl_today_species.setItemDelegate(self._delegate_today)
        card.body().addWidget(self.tbl_today_species)

        hint = QLabel("双击任一行可修改 / 删除；也可点击「添加或修改」")
        hint.setStyleSheet(f"color:{theme.FG_HINT};font-size:9pt;background:transparent;")
        card.body().addWidget(hint)

        op_row = QHBoxLayout()
        self.btn_add_today = IconButton("添加或修改", icon="plus")
        self.btn_add_today.clicked.connect(self._on_add_today_species)
        self.btn_reset_today = IconButton("清空今日统计", icon="trash", danger=True)
        self.btn_reset_today.clicked.connect(self._on_reset_today)
        op_row.addWidget(self.btn_add_today)
        op_row.addStretch(1)
        op_row.addWidget(self.btn_reset_today)
        card.body().addLayout(op_row)

        v.addWidget(card, 1)
        return w

    def _on_reset_today(self):
        r = QMessageBox.question(
            self,
            "确认",
            "确定要清空今日所有污染统计吗？此操作不可撤销。",
        )
        if r == QMessageBox.StandardButton.Yes:
            self.reset_today_requested.emit()

    # ================================================================
    # 设置 tab
    # ================================================================

    def _build_settings_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)

        # 热键分组
        gb_hk = QGroupBox("全局热键（直接键入字符，如 8 / f2 / ctrl+n）")
        hk_layout = QFormLayout(gb_hk)
        self._hk_edits: Dict[str, QLineEdit] = {}
        for key, label in HOTKEY_ACTIONS:
            le = QLineEdit()
            le.setPlaceholderText("例如 8 / f2 / ctrl+shift+p")
            le.editingFinished.connect(self._on_hotkey_changed)
            hk_layout.addRow(label, le)
            self._hk_edits[key] = le
        v.addWidget(gb_hk)

        # 识别区域 / 分辨率
        gb_res = QGroupBox("识别区域 / 分辨率")
        res_layout = QFormLayout(gb_res)

        # 识别游戏窗口（推荐首选）
        self.btn_detect_game = IconButton("识别游戏窗口", icon="eye", primary=True)
        self.btn_detect_game.clicked.connect(self._on_detect_game_window)
        self.lbl_game_window = QLabel("未识别")
        self.lbl_game_window.setStyleSheet(
            f"color:{theme.FG_DIM};background:transparent;padding-left:6px;"
        )
        detect_row = QHBoxLayout()
        detect_row.addWidget(self.btn_detect_game)
        detect_row.addWidget(self.lbl_game_window, 1)
        detect_wrap = QWidget()
        detect_wrap.setLayout(detect_row)
        res_layout.addRow("一键适配:", detect_wrap)

        # 手动分辨率预设（作为备选）
        self.cb_resolution = QComboBox()
        self.cb_resolution.setEditable(True)
        self.cb_resolution.addItems(BUILTIN_RESOLUTIONS)
        self.btn_apply_resolution = IconButton("应用")
        self.btn_apply_resolution.clicked.connect(self._on_apply_resolution)
        self.btn_preview_regions = IconButton("预览识别区域", icon="eye")
        self.btn_preview_regions.clicked.connect(self._on_preview_regions)
        res_row = QHBoxLayout()
        res_row.addWidget(self.cb_resolution, 1)
        res_row.addWidget(self.btn_apply_resolution)
        res_row.addWidget(self.btn_preview_regions)
        res_wrap = QWidget()
        res_wrap.setLayout(res_row)
        res_layout.addRow("分辨率预设:", res_wrap)

        self.le_model_dir = QLineEdit()
        self.le_model_dir.editingFinished.connect(self._on_model_dir_changed)
        res_layout.addRow("PaddleOCR 模型目录:", self.le_model_dir)

        v.addWidget(gb_res)

        # 检测参数
        gb_det = QGroupBox("检测参数")
        det_layout = QFormLayout(gb_det)
        self.sp_cooldown = QDoubleSpinBox()
        self.sp_cooldown.setRange(8.0, 60.0)
        self.sp_cooldown.setSingleStep(0.5)
        self.sp_cooldown.setSuffix(" 秒")
        self.sp_cooldown.valueChanged.connect(self._on_cooldown_changed)
        det_layout.addRow("命中冷却:", self.sp_cooldown)

        self.sp_scan = QDoubleSpinBox()
        self.sp_scan.setRange(0.2, 3.0)
        self.sp_scan.setSingleStep(0.1)
        self.sp_scan.setSuffix(" 秒")
        self.sp_scan.valueChanged.connect(self._on_scan_changed)
        det_layout.addRow("扫描间隔:", self.sp_scan)

        self.sp_delay = QDoubleSpinBox()
        self.sp_delay.setRange(0.0, 3.0)
        self.sp_delay.setSingleStep(0.1)
        self.sp_delay.setSuffix(" 秒")
        self.sp_delay.valueChanged.connect(self._on_delay_changed)
        det_layout.addRow("命中后等待名称稳定:", self.sp_delay)

        v.addWidget(gb_det)
        v.addStretch(1)
        return w

    def _on_hotkey_changed(self):
        if self._controller is None:
            return
        hk = self._controller.config.setdefault("hotkeys", {})
        for k, le in self._hk_edits.items():
            hk[k] = le.text().strip().lower()
        self._controller.mark_config_dirty()
        self.hotkeys_changed.emit()

    def _on_apply_resolution(self):
        if self._controller is None:
            return
        from ..backend.utils import apply_resolution_preset
        preset = self.cb_resolution.currentText().strip()
        mode = apply_resolution_preset(self._controller.config, preset)
        self._controller.mark_config_dirty()
        QMessageBox.information(self, "分辨率切换", f"已应用：{preset}（{mode}）")

    def _on_model_dir_changed(self):
        if self._controller is None:
            return
        self._controller.config["paddleocr_model_dir"] = self.le_model_dir.text().strip() or "paddleocr_models"
        self._controller.mark_config_dirty()

    def _on_cooldown_changed(self, v: float):
        if self._controller is None:
            return
        self._controller.config["cooldown_seconds"] = float(v)
        self._controller.mark_config_dirty()

    def _on_scan_changed(self, v: float):
        if self._controller is None:
            return
        self._controller.config["scan_interval"] = float(v)
        self._controller.mark_config_dirty()

    def _on_delay_changed(self, v: float):
        if self._controller is None:
            return
        self._controller.config["name_read_delay"] = float(v)
        self._controller.mark_config_dirty()

    def _on_detect_game_window(self):
        if self._controller is None:
            return
        info = self._controller.detect_game_window()
        if info is None:
            self.lbl_game_window.setText("未检测到游戏窗口")
            self.lbl_game_window.setStyleSheet(
                f"color:{theme.FG_DANGER};background:transparent;padding-left:6px;"
            )
            QMessageBox.warning(
                self, "未找到游戏窗口",
                "未检测到洛克王国游戏窗口。\n请确认游戏已启动并处于前台，或使用下方分辨率预设手动设置。",
            )
            return
        self.lbl_game_window.setText(
            f"{info['title']}   {info['w']}x{info['h']}   偏移 ({info['x']},{info['y']})"
        )
        self.lbl_game_window.setStyleSheet(
            f"color:{theme.FG_SUCCESS};background:transparent;padding-left:6px;"
        )
        # 同步更新分辨率下拉
        res_str = f"{info['w']}x{info['h']}"
        idx = self.cb_resolution.findText(res_str)
        if idx >= 0:
            self.cb_resolution.setCurrentIndex(idx)
        else:
            self.cb_resolution.setEditText(res_str)

    def _on_preview_regions(self):
        """在屏幕上以半透明方块显示 3 个检测区域 5 秒。"""
        if self._controller is None:
            return
        cfg = self._controller.config
        from .region_preview import RegionPreview
        self._region_preview = RegionPreview(
            middle=cfg.get("middle_region", {}),
            header=cfg.get("header_region", {}),
            name_rel=cfg.get("name_in_header", {}),
        )
        self._region_preview.show_for(5000)

    # ================================================================
    # 统计 tab
    # ================================================================

    def _build_stats_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(4, 4, 4, 4)
        v.setSpacing(theme.SPACE_MD)

        card1 = Card(padding=14)
        card1.body().addWidget(
            SectionHeader("历史精灵累计", icon="chart", subtitle="双击修改累计次数")
        )
        self.tbl_species_total = QTableWidget(0, 2)
        self.tbl_species_total.setHorizontalHeaderLabels(["精灵", "累计次数"])
        self.tbl_species_total.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.tbl_species_total.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        self.tbl_species_total.verticalHeader().setVisible(False)
        self.tbl_species_total.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tbl_species_total.setAlternatingRowColors(True)
        self.tbl_species_total.cellDoubleClicked.connect(self._on_edit_total_row)
        self.tbl_species_total.verticalHeader().setDefaultSectionSize(32)
        self._delegate_total = CountBarDelegate(value_column=1)
        self.tbl_species_total.setItemDelegate(self._delegate_total)
        card1.body().addWidget(self.tbl_species_total)

        ops1 = QHBoxLayout()
        self.btn_add_total = IconButton("添加或修改", icon="plus")
        self.btn_add_total.clicked.connect(self._on_add_total_species)
        ops1.addWidget(self.btn_add_total)
        ops1.addStretch(1)
        card1.body().addLayout(ops1)

        v.addWidget(card1, 1)

        card2 = Card(padding=14)
        header_row = QHBoxLayout()
        header_row.addWidget(
            SectionHeader("每日污染总数", icon="chart", subtitle="双击修改某一天的总数"), 1
        )
        # 右侧嵌入 7 天 spark-line
        self.spark_daily = SparkLine([], line_color=theme.BG_ACCENT_HI)
        self.spark_daily.setFixedSize(140, 36)
        header_row.addWidget(self.spark_daily, 0, Qt.AlignmentFlag.AlignVCenter)
        header_wrap = QWidget()
        header_wrap.setLayout(header_row)
        card2.body().addWidget(header_wrap)

        self.tbl_daily = QTableWidget(0, 2)
        self.tbl_daily.setHorizontalHeaderLabels(["日期", "总次数"])
        self.tbl_daily.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.tbl_daily.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        self.tbl_daily.verticalHeader().setVisible(False)
        self.tbl_daily.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tbl_daily.setAlternatingRowColors(True)
        self.tbl_daily.cellDoubleClicked.connect(self._on_edit_daily_row)
        card2.body().addWidget(self.tbl_daily)

        ops2 = QHBoxLayout()
        self.btn_add_daily = IconButton("添加或修改某一天", icon="plus")
        self.btn_add_daily.clicked.connect(self._on_add_daily)
        ops2.addWidget(self.btn_add_daily)
        ops2.addStretch(1)
        card2.body().addLayout(ops2)

        v.addWidget(card2, 1)
        return w

    # ---- 统计修改事件处理 ----

    @staticmethod
    def _row_name_value(tbl: QTableWidget, row: int) -> Tuple[str, int]:
        name = tbl.item(row, 0).text() if tbl.item(row, 0) else ""
        try:
            value = int(tbl.item(row, 1).text()) if tbl.item(row, 1) else 0
        except ValueError:
            value = 0
        return name, value

    def _on_edit_today_row(self, row: int, _col: int):
        if self._controller is None:
            return
        name, value = self._row_name_value(self.tbl_today_species, row)
        if not name:
            return
        res = edit_count_dialog(
            self, title=f"修改今日：{name}",
            name=name, value=value, name_locked=True, allow_delete=True,
        )
        if res is None:
            return
        new_name, new_val, deleted = res
        if deleted:
            self._controller.delete_today_species(new_name)
        else:
            self._controller.set_today_species(new_name, new_val)

    def _on_add_today_species(self):
        if self._controller is None:
            return
        res = edit_count_dialog(
            self, title="添加 / 修改今日精灵",
            name="", value=1, name_locked=False, allow_delete=False,
        )
        if res is None:
            return
        new_name, new_val, _ = res
        self._controller.set_today_species(new_name, new_val)

    def _on_edit_total_row(self, row: int, _col: int):
        if self._controller is None:
            return
        name, value = self._row_name_value(self.tbl_species_total, row)
        if not name:
            return
        res = edit_count_dialog(
            self, title=f"修改累计：{name}",
            name=name, value=value, name_locked=True, allow_delete=True,
        )
        if res is None:
            return
        new_name, new_val, deleted = res
        if deleted:
            self._controller.delete_species_total(new_name)
        else:
            self._controller.set_species_total(new_name, new_val)

    def _on_add_total_species(self):
        if self._controller is None:
            return
        res = edit_count_dialog(
            self, title="添加 / 修改累计精灵",
            name="", value=1, name_locked=False, allow_delete=False,
        )
        if res is None:
            return
        new_name, new_val, _ = res
        self._controller.set_species_total(new_name, new_val)

    def _on_edit_daily_row(self, row: int, _col: int):
        if self._controller is None:
            return
        day_item = self.tbl_daily.item(row, 0)
        val_item = self.tbl_daily.item(row, 1)
        if day_item is None:
            return
        day = day_item.text()
        try:
            value = int(val_item.text()) if val_item else 0
        except ValueError:
            value = 0
        res = edit_daily_dialog(
            self, title=f"修改 {day} 总数",
            day=day, value=value, day_locked=True,
        )
        if res is None:
            return
        new_day, new_val = res
        self._controller.set_daily_total(new_day, new_val)

    def _on_add_daily(self):
        if self._controller is None:
            return
        from datetime import date
        today = date.today().isoformat()
        res = edit_daily_dialog(
            self, title="添加 / 修改某一天总数",
            day=today, value=0, day_locked=False,
        )
        if res is None:
            return
        new_day, new_val = res
        self._controller.set_daily_total(new_day, new_val)

    # ================================================================
    # 关于 tab
    # ================================================================

    def _build_about_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setSpacing(12)

        title = QLabel(f"<b>污染计数器 {APP_VERSION}</b>")
        title.setStyleSheet("font-size:16pt;")
        v.addWidget(title)

        v.addWidget(QLabel("洛克王国世界污染追踪桌面工具（PyQt6 重写版）。"))

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self.btn_donate = IconButton("打赏作者", icon="sparkle", primary=True)
        self.btn_check_update = IconButton("检查更新", icon="refresh")
        self.btn_open_release = IconButton("发布页", icon="window")
        self.btn_open_repo = IconButton("项目主页", icon="info")
        btn_row.addWidget(self.btn_donate)
        btn_row.addWidget(self.btn_check_update)
        btn_row.addWidget(self.btn_open_release)
        btn_row.addWidget(self.btn_open_repo)
        btn_row.addStretch(1)
        v.addLayout(btn_row)

        self.btn_donate.clicked.connect(self._on_donate)
        self.btn_check_update.clicked.connect(self._on_check_update)
        self.btn_open_release.clicked.connect(self._on_open_release)
        self.btn_open_repo.clicked.connect(self._on_open_repo)

        self.txt_update_log = QLabel("")
        self.txt_update_log.setWordWrap(True)
        self.txt_update_log.setStyleSheet(
            f"background-color:{theme.BG_PANEL};border:1px solid {theme.BORDER};"
            f"padding:10px;border-radius:8px;color:{theme.FG_TEXT};"
        )
        v.addWidget(self.txt_update_log, 1)
        return w

    def _on_donate(self):
        from .donate_dialog import DonateDialog
        DonateDialog(self).exec()

    def _on_open_release(self):
        url = (self._controller.config if self._controller else {}).get(
            "release_page_url",
            "https://github.com/YUZE04/Roco-pollution-counter/releases/latest",
        )
        webbrowser.open(url)

    def _on_open_repo(self):
        webbrowser.open("https://github.com/YUZE04/Roco-pollution-counter")

    def _on_check_update(self):
        if self._controller is None:
            return
        url = str(self._controller.config.get("update_info_url", "")).strip()
        if not url:
            QMessageBox.warning(self, "检查更新", "未配置 update_info_url")
            return
        self.btn_check_update.setEnabled(False)
        self.txt_update_log.setText("正在检查更新…")
        self._update_worker = UpdateCheckWorker(url)
        self._update_worker.finished_with_result.connect(self._on_update_result)
        self._update_worker.failed.connect(self._on_update_failed)
        self._update_worker.start()

    def _on_update_result(self, data: dict):
        self.btn_check_update.setEnabled(True)
        remote = str(data.get("version", "")).strip()
        title = str(data.get("title", "")).strip()
        notes = data.get("notes", [])
        notes_text = "\n".join(f"· {n}" for n in notes if isinstance(n, str))
        current = APP_VERSION
        msg = (
            f"<b>远端版本：</b>{remote or '(未知)'}<br>"
            f"<b>当前版本：</b>{current}<br>"
            f"<b>标题：</b>{title}<br><br>"
            f"<b>更新说明：</b><br>{notes_text.replace(chr(10), '<br>')}"
        )
        self.txt_update_log.setText(msg)
        try:
            if remote and self._version_cmp(remote, current) > 0:
                if QMessageBox.question(
                    self,
                    "发现新版本",
                    f"有新版本 {remote}，是否打开发布页下载？",
                ) == QMessageBox.StandardButton.Yes:
                    self._on_open_release()
        except Exception:
            pass

    def _on_update_failed(self, err: str):
        self.btn_check_update.setEnabled(True)
        self.txt_update_log.setText(f"检查更新失败：{err}")

    @staticmethod
    def _version_cmp(a: str, b: str) -> int:
        import re
        def tup(s):
            nums = re.findall(r"\d+", str(s))
            return tuple(int(x) for x in nums[:4]) if nums else (0,)
        ta, tb = tup(a), tup(b)
        n = max(len(ta), len(tb))
        ta = ta + (0,) * (n - len(ta))
        tb = tb + (0,) * (n - len(tb))
        if ta > tb: return 1
        if ta < tb: return -1
        return 0

    # ================================================================
    # 数据同步
    # ================================================================

    def _load_from_config(self):
        c = self._controller
        if c is None:
            return
        cfg = c.config

        # 热键
        hk = cfg.get("hotkeys", {})
        for key, le in self._hk_edits.items():
            le.setText(str(hk.get(key, "")))

        # 分辨率
        active = str(cfg.get("active_resolution", "2560x1600_150缩放"))
        idx = self.cb_resolution.findText(active)
        if idx >= 0:
            self.cb_resolution.setCurrentIndex(idx)
        else:
            self.cb_resolution.setEditText(active)

        # OCR 目录
        self.le_model_dir.setText(str(cfg.get("paddleocr_model_dir", "paddleocr_models")))

        # 检测参数
        self.sp_cooldown.setValue(float(cfg.get("cooldown_seconds", 12.0)))
        self.sp_scan.setValue(float(cfg.get("scan_interval", 0.7)))
        self.sp_delay.setValue(float(cfg.get("name_read_delay", 0.0)))

        # 如果已识别过游戏窗口，显示缓存信息
        wo = cfg.get("window_offset") or {}
        if isinstance(wo, dict) and wo.get("w") and wo.get("h"):
            self.lbl_game_window.setText(
                f"{wo.get('w')}x{wo.get('h')}   偏移 ({wo.get('x', 0)},{wo.get('y', 0)})"
            )
            self.lbl_game_window.setStyleSheet(
                f"color:{theme.FG_DIM};background:transparent;padding-left:6px;"
            )

    def _refresh_stats_tab(self):
        if self._controller is None:
            return
        self._suppress_item_changed = True
        try:
            d = self._controller.data
            # 数字过渡动画（Spring）
            count_up(self.lbl_today_total, int(d.total_count), duration=500)
            self.lbl_last_species.setText(d.last_species or "无")

            # 今日精灵
            today = d.species_counts
            today_rows = sorted(today.items(), key=lambda kv: (-kv[1], kv[0]))
            self._fill_table(self.tbl_today_species, today_rows)
            self._delegate_today.set_max_value(
                max([v for _, v in today_rows] or [1])
            )
            # 累计
            totals = d.species_total_counts
            total_rows = sorted(totals.items(), key=lambda kv: (-kv[1], kv[0]))
            self._fill_table(self.tbl_species_total, total_rows)
            self._delegate_total.set_max_value(
                max([v for _, v in total_rows] or [1])
            )
            # 每日总数
            daily = d._data.get("daily_totals", {}) if hasattr(d, "_data") else {}
            daily_rows = sorted(daily.items(), key=lambda kv: kv[0], reverse=True)
            self._fill_table(self.tbl_daily, daily_rows)

            # 最近 7 天的 spark-line（按日期升序）
            if hasattr(self, "spark_daily"):
                last7 = sorted(daily.items(), key=lambda kv: kv[0])[-7:]
                self.spark_daily.set_values([float(v) for _, v in last7])
        finally:
            self._suppress_item_changed = False

    @staticmethod
    def _fill_table(tbl: QTableWidget, rows: List[Tuple[str, int]]):
        tbl.setRowCount(len(rows))
        for r, (k, v) in enumerate(rows):
            item_k = QTableWidgetItem(str(k))
            # key 列不可编辑
            item_k.setFlags(item_k.flags() & ~Qt.ItemFlag.ItemIsEditable)
            item_v = QTableWidgetItem(str(v))
            item_v.setTextAlignment(int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))
            tbl.setItem(r, 0, item_k)
            tbl.setItem(r, 1, item_v)

    # ---------- 表格编辑回调 ----------

    @staticmethod
    def _parse_int(text: str):
        try:
            return max(0, int(str(text).strip()))
        except Exception:
            return None

    def _on_today_species_changed(self, item: QTableWidgetItem):
        if self._suppress_item_changed or self._controller is None:
            return
        if item.column() != 1:
            return
        name_item = self.tbl_today_species.item(item.row(), 0)
        if name_item is None:
            return
        val = self._parse_int(item.text())
        if val is None:
            QTimer.singleShot(0, self._refresh_stats_tab)
            return
        self._controller.data.set_today_species_count(name_item.text(), val)
        self._controller.data_changed.emit()

    def _on_species_total_changed(self, item: QTableWidgetItem):
        if self._suppress_item_changed or self._controller is None:
            return
        if item.column() != 1:
            return
        name_item = self.tbl_species_total.item(item.row(), 0)
        if name_item is None:
            return
        val = self._parse_int(item.text())
        if val is None:
            QTimer.singleShot(0, self._refresh_stats_tab)
            return
        self._controller.data.set_species_total_count(name_item.text(), val)
        self._controller.data_changed.emit()

    def _on_daily_total_changed(self, item: QTableWidgetItem):
        if self._suppress_item_changed or self._controller is None:
            return
        if item.column() != 1:
            return
        day_item = self.tbl_daily.item(item.row(), 0)
        if day_item is None:
            return
        val = self._parse_int(item.text())
        if val is None:
            QTimer.singleShot(0, self._refresh_stats_tab)
            return
        self._controller.data.set_daily_total(day_item.text(), val)
        self._controller.data_changed.emit()
