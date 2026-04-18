"""自定义无边框标题栏。

特点：
* 左：应用图标 + 标题；
* 右：最小化 / 最大化(还原) / 关闭三个矢量图标按钮；
* 拖动：优先使用 ``windowHandle().startSystemMove()`` 获得原生系统手势（贴边、
  Windows 11 吸附等）；不可用时回退到手动 move；
* 双击：最大化 / 还原切换；
* 背景色与应用主题一致（``BG_TITLE``），无"白色原生标题栏"违和感。
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QPoint, QSize, Qt
from PyQt6.QtGui import QIcon, QMouseEvent, QPixmap
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QWidget,
)

from . import theme
from .icons import paint_icon


_TITLE_BAR_HEIGHT = 36
_BTN_W = 44


class _CaptionButton(QPushButton):
    """标题栏右上角窗口按钮（min/max/close）。"""

    def __init__(
        self,
        icon_name: str,
        *,
        hover_color: str = theme.BG_ELEV,
        hover_text: str = theme.FG_TEXT,
        is_close: bool = False,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._icon_name = icon_name
        self._is_close = is_close
        self.setFixedSize(_BTN_W, _TITLE_BAR_HEIGHT)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self._apply_icon(theme.FG_DIM)

        if is_close:
            hover_bg = "#e04664"
            hover_fg = "#ffffff"
        else:
            hover_bg = hover_color
            hover_fg = hover_text

        self.setStyleSheet(
            f"QPushButton{{"
            f"  background-color:transparent;"
            f"  border:none;"
            f"  padding:0;"
            f"}}"
            f"QPushButton:hover{{"
            f"  background-color:{hover_bg};"
            f"}}"
            f"QPushButton:pressed{{"
            f"  background-color:{hover_bg};"
            f"}}"
        )

        self._hover_fg = hover_fg
        self.enterEvent = self._on_enter  # type: ignore[assignment]
        self.leaveEvent = self._on_leave  # type: ignore[assignment]

    def _apply_icon(self, color: str) -> None:
        pm = paint_icon(self._icon_name, 12, color)
        icon = QIcon(pm)
        self.setIcon(icon)
        self.setIconSize(QSize(12, 12))

    def _on_enter(self, _e) -> None:
        self._apply_icon(self._hover_fg)

    def _on_leave(self, _e) -> None:
        self._apply_icon(theme.FG_DIM)

    def set_icon_name(self, name: str) -> None:
        self._icon_name = name
        self._apply_icon(theme.FG_DIM)


class TitleBar(QWidget):
    """自定义窗口标题栏。"""

    def __init__(self, window: QWidget, title: str = "", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._window = window
        self.setFixedHeight(_TITLE_BAR_HEIGHT)
        self.setAutoFillBackground(True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName("TitleBar")
        self.setStyleSheet(
            f"#TitleBar{{"
            f"  background-color:{theme.BG_TITLE};"
            f"  border-bottom:1px solid {theme.BG_ELEV};"
            f"}}"
        )

        row = QHBoxLayout(self)
        row.setContentsMargins(12, 0, 0, 0)
        row.setSpacing(8)

        # 应用图标
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(16, 16)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._set_app_icon()
        row.addWidget(self.icon_label)

        # 标题
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet(
            f"color:{theme.FG_TEXT};"
            f"font-size:10pt;"
            f"font-weight:600;"
            f"background:transparent;"
            f"letter-spacing:0.3px;"
        )
        self.title_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        row.addWidget(self.title_label, 1)

        # 窗口按钮
        self.btn_min = _CaptionButton("minus")
        self.btn_max = _CaptionButton("window")
        self.btn_close = _CaptionButton("close", is_close=True)

        self.btn_min.clicked.connect(self._on_minimize)
        self.btn_max.clicked.connect(self._on_toggle_max)
        self.btn_close.clicked.connect(self._on_close)

        row.addWidget(self.btn_min)
        row.addWidget(self.btn_max)
        row.addWidget(self.btn_close)

        # 拖动回退用
        self._drag_offset: Optional[QPoint] = None

    # ---------- 图标 / 标题 ----------

    def _set_app_icon(self) -> None:
        icon = self._window.windowIcon()
        if icon is not None and not icon.isNull():
            pm = icon.pixmap(16, 16)
            if not pm.isNull():
                self.icon_label.setPixmap(pm)
                return
        # 回退到内置 sparkle 图标
        self.icon_label.setPixmap(paint_icon("sparkle", 16, theme.FG_SPECIES))

    def set_title(self, text: str) -> None:
        self.title_label.setText(text)

    def refresh_icon(self) -> None:
        self._set_app_icon()

    # ---------- 窗口按钮动作 ----------

    def _on_minimize(self) -> None:
        self._window.showMinimized()

    def _on_toggle_max(self) -> None:
        if self._window.isMaximized():
            self._window.showNormal()
            self.btn_max.set_icon_name("window")
        else:
            self._window.showMaximized()
            # 用"两个小方块"的视觉提示还原；这里沿用 window 图标以保持简洁
            self.btn_max.set_icon_name("window")

    def _on_close(self) -> None:
        self._window.close()

    # ---------- 拖动 / 双击最大化 ----------

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
        # 优先走系统原生拖动（贴边吸附等手势）
        handle = self._window.windowHandle()
        if handle is not None:
            try:
                if handle.startSystemMove():
                    event.accept()
                    return
            except Exception:
                pass
        # 回退：手动记录偏移
        self._drag_offset = (
            event.globalPosition().toPoint() - self._window.frameGeometry().topLeft()
        )
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_offset is None:
            return
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._window.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()

    def mouseReleaseEvent(self, _event: QMouseEvent) -> None:
        self._drag_offset = None

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._on_toggle_max()
            event.accept()
