"""右下角堆叠式 Toast 通知。

用法::

    from app.ui.toast import ToastManager
    self._toasts = ToastManager(self)         # parent = 主窗口
    self._toasts.show("+1 恶魔狼")

所有 toast 自动在 2.5s 后淡出；新 toast 会从下方堆入。
"""

from __future__ import annotations

from typing import List, Optional

from PyQt6.QtCore import (
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    QRect,
    QTimer,
    Qt,
)
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QWidget,
)

from . import theme
from .icons import paint_icon


_TOAST_W = 260
_TOAST_H = 38
_TOAST_GAP = 8
_MARGIN = 16
_DURATION_MS = 2400


class _Toast(QFrame):
    """单条 Toast，绝对定位到父窗口的右下角。

    用 QFrame + QSS 而非自绘，避免 QGraphicsOpacityEffect 的 painter 冲突。
    """

    def __init__(self, parent: QWidget, text: str, icon: Optional[str] = None):
        super().__init__(parent)
        self.setObjectName("Toast")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedSize(_TOAST_W, _TOAST_H)
        self.setStyleSheet(
            "#Toast{"
            "  background-color: rgba(35, 23, 56, 235);"
            "  border: 1px solid rgba(138, 85, 255, 140);"
            "  border-radius: 10px;"
            "}"
        )

        row = QHBoxLayout(self)
        row.setContentsMargins(12, 0, 12, 0)
        row.setSpacing(10)

        if icon:
            ico = QLabel()
            ico.setFixedSize(14, 14)
            ico.setPixmap(paint_icon(icon, 14, theme.FG_SPECIES))
            ico.setStyleSheet("background: transparent;")
            row.addWidget(ico)

        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color:{theme.FG_TEXT};background:transparent;font-size:10pt;"
        )
        lbl.setFont(QFont(theme.FONT_FAMILY, 10))
        row.addWidget(lbl, 1)

        # 透明度动画基础（现在只作用于本 QFrame 的 composite，不与 paintEvent 冲突）
        self._effect = QGraphicsOpacityEffect(self)
        self._effect.setOpacity(0.0)
        self.setGraphicsEffect(self._effect)


class ToastManager:
    """维护一个 toast 栈，负责布局和生命周期。"""

    def __init__(self, host: QWidget):
        self._host = host
        self._stack: List[_Toast] = []

    def show(self, text: str, icon: Optional[str] = "sparkle") -> None:
        t = _Toast(self._host, text, icon)
        t.show()
        self._stack.append(t)
        self._reposition()
        self._fade_in(t)
        # 到点后淡出
        QTimer.singleShot(_DURATION_MS, lambda: self._fade_out(t))

    # ---- 内部：布局 ----

    def _reposition(self) -> None:
        host_rect: QRect = self._host.rect()
        x = host_rect.right() - _TOAST_W - _MARGIN
        base_y = host_rect.bottom() - _TOAST_H - _MARGIN
        for i, t in enumerate(reversed(self._stack)):
            y = base_y - i * (_TOAST_H + _TOAST_GAP)
            t.move(x, y)

    # ---- 动画 ----

    def _fade_in(self, t: _Toast) -> None:
        # 从下方 + 6px 滑入
        start = t.pos()
        t.move(start.x(), start.y() + 6)
        pos_anim = QPropertyAnimation(t, b"pos", t)
        pos_anim.setDuration(220)
        pos_anim.setStartValue(t.pos())
        pos_anim.setEndValue(start)
        pos_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        pos_anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

        opacity_anim = QPropertyAnimation(t._effect, b"opacity", t)
        opacity_anim.setDuration(220)
        opacity_anim.setStartValue(0.0)
        opacity_anim.setEndValue(1.0)
        opacity_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        opacity_anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

    def _fade_out(self, t: _Toast) -> None:
        if t not in self._stack:
            return
        opacity_anim = QPropertyAnimation(t._effect, b"opacity", t)
        opacity_anim.setDuration(240)
        opacity_anim.setStartValue(1.0)
        opacity_anim.setEndValue(0.0)
        opacity_anim.setEasingCurve(QEasingCurve.Type.InCubic)

        def _cleanup():
            try:
                self._stack.remove(t)
            except ValueError:
                pass
            t.deleteLater()
            self._reposition()

        opacity_anim.finished.connect(_cleanup)
        opacity_anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
