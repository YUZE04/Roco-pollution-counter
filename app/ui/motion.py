"""Motion AI Kit —— 轻量级 Qt 动画工具箱。

关键函数（均为一行即可调用）：

* ``fade_in(widget, duration=220)`` — 透明度 0→1
* ``slide_in(widget, dy=12, duration=260)`` — 下移淡入组合
* ``count_up(label, to_value, duration=450)`` — 数字过渡（整型）
* ``pulse(widget, period_ms=1600)`` — 呼吸式缩放（适合状态指示灯）
* ``hover_lift(button, lift=1)`` — 悬停抬起 1px 的微反馈

所有动画使用 ``OutCubic`` 作为默认缓动——与系统原生动画风格一致。
"""

from __future__ import annotations

from typing import Callable, Optional

from PyQt6.QtCore import (
    QEasingCurve,
    QEvent,
    QObject,
    QPropertyAnimation,
    QTimer,
    QVariantAnimation,
    Qt,
)
from PyQt6.QtWidgets import QGraphicsOpacityEffect, QLabel, QWidget


# ---------------- 基础 ----------------

def _ensure_opacity(widget: QWidget) -> QGraphicsOpacityEffect:
    eff = widget.graphicsEffect()
    if not isinstance(eff, QGraphicsOpacityEffect):
        eff = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(eff)
    return eff


def fade_in(widget: QWidget, duration: int = 220, start: float = 0.0) -> QPropertyAnimation:
    eff = _ensure_opacity(widget)
    eff.setOpacity(start)
    anim = QPropertyAnimation(eff, b"opacity", widget)
    anim.setDuration(duration)
    anim.setStartValue(start)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
    return anim


def slide_in(widget: QWidget, dy: int = 12, duration: int = 260, with_fade: bool = False) -> None:
    """从当前位置下方 *dy* 像素滑入。

    ``with_fade=True`` 会额外挂一个 ``QGraphicsOpacityEffect``。注意：在
    ``FramelessWindowHint + WA_TranslucentBackground`` 的窗口里这会与子控件
    的 QPainter 冲突产生重影，默认关闭。
    """
    if with_fade:
        fade_in(widget, duration=duration)
    start_pos = widget.pos()
    widget.move(start_pos.x(), start_pos.y() + dy)
    anim = QPropertyAnimation(widget, b"pos", widget)
    anim.setDuration(duration)
    anim.setStartValue(widget.pos())
    anim.setEndValue(start_pos)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)


def count_up(
    label: QLabel,
    to_value: int,
    duration: int = 500,
    formatter: Optional[Callable[[int], str]] = None,
    spring: bool = True,
) -> None:
    """让 ``label`` 的整型文本从当前值动画过渡到 ``to_value``。

    ``spring=True`` 使用 OutBack（带轻微回弹），更像 iOS/Arc 的数字过渡。
    """
    fmt = formatter or (lambda v: str(v))
    try:
        from_value = int(str(label.text()).strip() or "0")
    except ValueError:
        from_value = 0
    if from_value == to_value:
        label.setText(fmt(to_value))
        return

    anim = QVariantAnimation(label)
    anim.setDuration(duration)
    anim.setStartValue(from_value)
    anim.setEndValue(to_value)
    if spring:
        curve = QEasingCurve(QEasingCurve.Type.OutBack)
        curve.setOvershoot(1.2)  # 轻微回弹，不过头
        anim.setEasingCurve(curve)
    else:
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    anim.valueChanged.connect(lambda v: label.setText(fmt(int(v))))
    anim.finished.connect(lambda: label.setText(fmt(to_value)))
    anim.start(QVariantAnimation.DeletionPolicy.DeleteWhenStopped)
    # 防止 GC
    label._count_up_anim = anim  # type: ignore[attr-defined]


# ---------------- 呼吸 / 悬停 ----------------

class _Pulser(QObject):
    """通过 QTimer 生成 0..1..0 的呼吸值，派发给回调。"""

    def __init__(self, parent: QWidget, period_ms: int, on_phase: Callable[[float], None]):
        super().__init__(parent)
        self._t = 0
        self._period = max(200, int(period_ms))
        self._cb = on_phase
        self._timer = QTimer(self)
        self._timer.setInterval(33)  # ~30fps
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def _tick(self) -> None:
        import math
        self._t = (self._t + 33) % self._period
        phase = 0.5 - 0.5 * math.cos(2 * math.pi * self._t / self._period)
        self._cb(phase)


def pulse_signal(parent: QWidget, period_ms: int, on_phase: Callable[[float], None]) -> _Pulser:
    """驱动一个 0..1 的呼吸值（用于在 paintEvent 中做自定义绘制）。返回 Pulser 以便停止。"""
    return _Pulser(parent, period_ms, on_phase)


class _HoverLift(QObject):
    def __init__(self, w: QWidget, lift: int):
        super().__init__(w)
        self._w = w
        self._lift = lift
        w.installEventFilter(self)

    def eventFilter(self, obj, event: QEvent) -> bool:  # noqa: D401
        if obj is self._w:
            if event.type() == QEvent.Type.Enter:
                self._w.move(self._w.x(), self._w.y() - self._lift)
            elif event.type() == QEvent.Type.Leave:
                self._w.move(self._w.x(), self._w.y() + self._lift)
        return False


def hover_lift(w: QWidget, lift: int = 1) -> _HoverLift:
    return _HoverLift(w, lift)


# ---------------- Tab 切换过渡 ----------------

def animate_tab_switch(widget: QWidget, duration: int = 220, dx: int = 10) -> None:
    """给刚切出的 tab 内容加一段横向滑入（纯位移，不用 opacity effect
    以避免 frameless + Mica 下的绘制冲突）。"""
    if widget is None:
        return
    base_pos = widget.pos()
    widget.move(base_pos.x() + dx, base_pos.y())
    anim = QPropertyAnimation(widget, b"pos", widget)
    anim.setDuration(duration)
    anim.setStartValue(widget.pos())
    anim.setEndValue(base_pos)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
