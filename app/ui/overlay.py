"""真正的桌面悬浮窗。

特性：
- 无边框、始终置顶、不在任务栏出现
- 半透明紫黑底 + 荧光紫边
- 锁定时点击穿透（`Qt.WindowTransparentForInput`），鼠标完全透传到游戏
- 解锁时可拖动、可通过上下文菜单操作
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, QPoint, QVariantAnimation, QEasingCurve, pyqtSignal
from PyQt6.QtGui import (
    QAction,
    QBrush,
    QColor,
    QCursor,
    QFont,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)
from PyQt6.QtWidgets import QMenu, QWidget

from . import theme
from .icons import paint_icon
from .motion import pulse_signal


class OverlayWindow(QWidget):
    """极简悬浮计数窗。

    信号：
        toggle_lock_requested: 用户请求切换锁定状态
        toggle_monitor_requested: 用户请求切换监测开/关
        show_main_requested: 用户请求打开主配置窗
        manual_add_requested / manual_sub_requested: 手动加/减
        quit_requested: 退出程序
    """

    toggle_lock_requested = pyqtSignal()
    toggle_monitor_requested = pyqtSignal()
    show_main_requested = pyqtSignal()
    manual_add_requested = pyqtSignal()
    manual_sub_requested = pyqtSignal()
    quit_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        # 窗口标志：无边框 + 置顶 + Tool（不出现在任务栏）+ 不激活
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        # 初始大小
        self.resize(260, 150)

        # 运行时状态（由外部 set_* 方法写入）
        self._total_count: int = 0
        self._display_count: float = 0.0       # count-up 动画的当前值
        self._species_name: str = "无"
        self._status_text: str = "未启动"
        self._species_list: list[tuple[str, int]] = []
        self._running: bool = False
        self._locked: bool = False
        self._hotkey_hint: str = ""
        self._pulse_phase: float = 0.0         # 0..1 的呼吸相位

        # 拖动状态
        self._drag_pos: QPoint | None = None

        # 动效：数字过渡
        self._count_anim: QVariantAnimation | None = None

        # 动效：状态点呼吸（监测中时活跃）
        def _on_phase(ph: float) -> None:
            self._pulse_phase = ph
            if self._running:
                self.update()
        self._pulser = pulse_signal(self, 1600, _on_phase)

        # 预渲染锁图标（小尺寸图标 pixmap 缓存）
        self._icon_lock = paint_icon("lock", 14, theme.FG_SPECIES)

    # ---------- 状态更新接口 ----------

    def set_total_count(self, count: int) -> None:
        target = int(count)
        if target == self._total_count:
            return
        self._total_count = target
        # 数字过渡（300ms）
        if self._count_anim is not None:
            self._count_anim.stop()
        anim = QVariantAnimation(self)
        anim.setDuration(320)
        anim.setStartValue(float(self._display_count))
        anim.setEndValue(float(target))
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        def _on_val(v):
            self._display_count = float(v)
            self.update()

        anim.valueChanged.connect(_on_val)
        anim.finished.connect(lambda: setattr(self, "_display_count", float(target)))
        self._count_anim = anim
        anim.start(QVariantAnimation.DeletionPolicy.KeepWhenStopped)

    def set_current_species(self, name: str) -> None:
        self._species_name = name or "无"
        self.update()

    def set_status_text(self, text: str) -> None:
        self._status_text = text or ""
        self.update()

    def set_species_list(self, items: list[tuple[str, int]]) -> None:
        """items = [(name, count), ...]，外部负责排序。"""
        self._species_list = list(items)
        self._relayout()

    def set_hotkey_hint(self, text: str) -> None:
        self._hotkey_hint = str(text or "")
        self._relayout()

    def _relayout(self) -> None:
        # 根据条目数 + 是否有热键提示自动变长
        n = max(0, min(15, len(self._species_list)))
        # 标题/计数/当前精灵 ≈ 100 像素；每条物种 22；底部热键提示 22
        hint_h = 22 if self._hotkey_hint else 0
        target_h = 110 + n * 22 + hint_h + 14
        if target_h != self.height():
            self.resize(self.width(), target_h)
        self.update()

    def set_running(self, running: bool) -> None:
        self._running = bool(running)
        self.update()

    def set_locked(self, locked: bool) -> None:
        """锁定 → 点击穿透；解锁 → 可交互。"""
        self._locked = bool(locked)
        flags = self.windowFlags()
        if self._locked:
            flags |= Qt.WindowType.WindowTransparentForInput
        else:
            flags &= ~Qt.WindowType.WindowTransparentForInput
        # 切换 flags 后需要重新 show 生效
        was_visible = self.isVisible()
        self.setWindowFlags(flags)
        if was_visible:
            self.show()
        self.update()

    # ---------- 绘制 ----------

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        # 背景：圆角 + 顶部渐变高光
        rect = self.rect().adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(rect.toRectF(), 14, 14)

        bg_color = QColor(*theme.OVERLAY_BG_RGBA)
        if self._locked:
            bg_color.setAlpha(160)
        painter.fillPath(path, bg_color)

        # 顶部高光渐变（紫色玻璃感）
        grad = QLinearGradient(0, 0, 0, 60)
        grad.setColorAt(0.0, QColor(138, 85, 255, 55 if not self._locked else 30))
        grad.setColorAt(1.0, QColor(138, 85, 255, 0))
        painter.save()
        painter.setClipPath(path)
        painter.fillRect(self.rect(), grad)
        painter.restore()

        # 边框
        pen = QPen(QColor(*theme.OVERLAY_BORDER_RGBA), 1.2)
        painter.setPen(pen)
        painter.drawPath(path)

        # 标题栏：呼吸状态点 + 状态文本
        status_color = QColor(theme.FG_SUCCESS) if self._running else QColor("#888")
        dot_cx, dot_cy = 20, 20
        if self._running:
            halo_r = 10 + 6 * self._pulse_phase
            halo = QRadialGradient(dot_cx, dot_cy, halo_r)
            glow = QColor(status_color)
            glow.setAlpha(int(140 * (1 - self._pulse_phase)))
            halo.setColorAt(0.0, glow)
            halo.setColorAt(1.0, QColor(status_color.red(), status_color.green(), status_color.blue(), 0))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(halo))
            painter.drawEllipse(QPoint(dot_cx, dot_cy), int(halo_r), int(halo_r))

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(status_color)
        painter.drawEllipse(QPoint(dot_cx, dot_cy), 5, 5)

        painter.setPen(QColor(theme.FG_DIM))
        painter.setFont(QFont(theme.FONT_FAMILY, 9))
        status_text = self._status_text or ("监测中" if self._running else "未启动")
        text_x = 30
        if self._locked:
            painter.drawPixmap(text_x, 13, self._icon_lock)
            text_x += 18
        painter.drawText(text_x, 25, status_text)

        # 右上角右键菜单提示（仅未锁定时显示，锁定时无法右键）
        if not self._locked:
            tip_text = "右键菜单"
            painter.setPen(QColor(theme.FG_HINT))
            painter.setFont(QFont(theme.FONT_FAMILY, 8))
            # 先量一下文字宽度，贴右边画
            metrics = painter.fontMetrics()
            tw = metrics.horizontalAdvance(tip_text)
            tip_right_padding = 14
            tip_x = self.width() - tw - tip_right_padding
            # 背景胶囊
            cap_x = tip_x - 8
            cap_y = 10
            cap_w = tw + 16
            cap_h = 18
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(138, 85, 255, 35))
            painter.drawRoundedRect(cap_x, cap_y, cap_w, cap_h, 9, 9)
            painter.setPen(QColor(theme.FG_DIM))
            painter.drawText(tip_x, cap_y + 13, tip_text)

        # 大数字：今日总污染数（动画值）
        painter.setPen(QColor(theme.FG_COUNT))
        font_big = QFont(theme.FONT_FAMILY, 30, QFont.Weight.Bold)
        font_big.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, -1.0)
        painter.setFont(font_big)
        painter.drawText(
            14, 36, self.width() - 28, 50,
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            str(int(round(self._display_count))),
        )

        # 当前精灵
        painter.setPen(QColor(theme.FG_SPECIES))
        painter.setFont(QFont(theme.FONT_FAMILY, 11))
        painter.drawText(
            14, 80, self.width() - 28, 22,
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            f"当前: {self._species_name}",
        )

        # 精灵统计列表
        painter.setPen(QColor(theme.FG_TEXT))
        painter.setFont(QFont(theme.FONT_FAMILY, 9))
        y = 106
        for name, cnt in self._species_list[:15]:
            painter.drawText(14, y, self.width() - 28, 20,
                             int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                             f"{name}: {cnt}")
            y += 22

        # 底部热键提示
        if self._hotkey_hint:
            painter.setPen(QColor(theme.FG_HINT))
            painter.setFont(QFont(theme.FONT_FAMILY, 8))
            painter.drawText(14, self.height() - 24, self.width() - 28, 20,
                             int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                             self._hotkey_hint)

    # ---------- 鼠标交互（仅在未锁定时生效） ----------

    def mousePressEvent(self, event: QMouseEvent):
        if self._locked:
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._locked or self._drag_pos is None:
            return
        if event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, _event: QMouseEvent):
        self._drag_pos = None

    def contextMenuEvent(self, event):
        if self._locked:
            return
        from .icons import get_icon

        menu = QMenu(self)
        act_lock = QAction(get_icon("lock", 14, theme.FG_TEXT), "锁定悬浮窗 (点击穿透)", self)
        act_lock.triggered.connect(self.toggle_lock_requested.emit)
        act_toggle = QAction(
            get_icon("stop" if self._running else "play", 14, theme.FG_TEXT),
            "停止监测" if self._running else "开始监测",
            self,
        )
        act_toggle.triggered.connect(self.toggle_monitor_requested.emit)
        act_add = QAction(get_icon("plus", 14, theme.FG_TEXT), "手动加一次", self)
        act_add.triggered.connect(self.manual_add_requested.emit)
        act_sub = QAction(get_icon("minus", 14, theme.FG_TEXT), "手动减一次", self)
        act_sub.triggered.connect(self.manual_sub_requested.emit)
        act_main = QAction(get_icon("settings", 14, theme.FG_TEXT), "打开主窗口 / 设置", self)
        act_main.triggered.connect(self.show_main_requested.emit)
        act_quit = QAction(get_icon("power", 14, theme.FG_DANGER), "退出程序", self)
        act_quit.triggered.connect(self.quit_requested.emit)

        for a in (act_lock, act_toggle, act_add, act_sub, act_main, act_quit):
            menu.addAction(a)

        menu.exec(QCursor.pos())
