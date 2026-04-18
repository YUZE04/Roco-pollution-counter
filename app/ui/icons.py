"""Better Icons —— 纯 QPainter 矢量图标注册表。

用法::

    from app.ui.icons import get_icon
    btn.setIcon(get_icon("play", color="#fff", size=18))

特点：
- 零外部资源，打包体积无增量；
- 任意颜色 / 任意尺寸，HiDPI 下依然清晰；
- 图标用 path 命令描述，统一 24x24 viewBox，再等比缩放到目标尺寸。
"""

from __future__ import annotations

from typing import Callable, Dict, Optional

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt
from PyQt6.QtGui import (
    QColor,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)

# ---------- 绘制原语 ----------

def _new_canvas(size: int) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    return pm


def _stroked(painter: QPainter, color: QColor, width: float = 2.0) -> None:
    pen = QPen(color)
    pen.setWidthF(width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)


def _filled(painter: QPainter, color: QColor) -> None:
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)


# ---------- 具体图标（输入画笔已铺好色，viewBox 0..24） ----------

def _draw_play(p: QPainter, c: QColor) -> None:
    _filled(p, c)
    path = QPainterPath()
    path.moveTo(7, 5)
    path.lineTo(19, 12)
    path.lineTo(7, 19)
    path.closeSubpath()
    p.drawPath(path)


def _draw_stop(p: QPainter, c: QColor) -> None:
    _filled(p, c)
    p.drawRoundedRect(QRectF(6, 6, 12, 12), 2.2, 2.2)


def _draw_pause(p: QPainter, c: QColor) -> None:
    _filled(p, c)
    p.drawRoundedRect(QRectF(7, 5, 3.5, 14), 1.2, 1.2)
    p.drawRoundedRect(QRectF(13.5, 5, 3.5, 14), 1.2, 1.2)


def _draw_lock(p: QPainter, c: QColor) -> None:
    _stroked(p, c, 1.8)
    p.drawRoundedRect(QRectF(5.5, 10.5, 13, 9), 2, 2)
    path = QPainterPath()
    path.moveTo(8, 10.5)
    path.lineTo(8, 7.5)
    path.arcTo(QRectF(8, 3.5, 8, 8), 180, -180)
    path.lineTo(16, 10.5)
    p.drawPath(path)


def _draw_unlock(p: QPainter, c: QColor) -> None:
    _stroked(p, c, 1.8)
    p.drawRoundedRect(QRectF(5.5, 10.5, 13, 9), 2, 2)
    path = QPainterPath()
    path.moveTo(8, 10.5)
    path.lineTo(8, 7.5)
    path.arcTo(QRectF(8, 3.5, 8, 8), 180, -120)
    p.drawPath(path)


def _draw_plus(p: QPainter, c: QColor) -> None:
    _stroked(p, c, 2.2)
    p.drawLine(QPointF(12, 5), QPointF(12, 19))
    p.drawLine(QPointF(5, 12), QPointF(19, 12))


def _draw_minus(p: QPainter, c: QColor) -> None:
    _stroked(p, c, 2.2)
    p.drawLine(QPointF(5, 12), QPointF(19, 12))


def _draw_settings(p: QPainter, c: QColor) -> None:
    _stroked(p, c, 1.7)
    # 八齿齿轮
    import math
    cx, cy = 12, 12
    r_out, r_in = 9.0, 6.0
    path = QPainterPath()
    for i in range(16):
        a = math.radians(i * (360 / 16))
        r = r_out if i % 2 == 0 else r_in
        x = cx + r * math.cos(a)
        y = cy + r * math.sin(a)
        if i == 0:
            path.moveTo(x, y)
        else:
            path.lineTo(x, y)
    path.closeSubpath()
    p.drawPath(path)
    p.drawEllipse(QPointF(cx, cy), 2.2, 2.2)


def _draw_refresh(p: QPainter, c: QColor) -> None:
    _stroked(p, c, 1.8)
    path = QPainterPath()
    path.arcMoveTo(QRectF(4, 4, 16, 16), 40)
    path.arcTo(QRectF(4, 4, 16, 16), 40, 280)
    p.drawPath(path)
    # 箭头
    _filled(p, c)
    arrow = QPainterPath()
    arrow.moveTo(18.6, 4.8)
    arrow.lineTo(19.5, 9.6)
    arrow.lineTo(14.7, 8.7)
    arrow.closeSubpath()
    p.drawPath(arrow)


def _draw_power(p: QPainter, c: QColor) -> None:
    _stroked(p, c, 1.9)
    path = QPainterPath()
    path.arcMoveTo(QRectF(4, 4, 16, 16), 120)
    path.arcTo(QRectF(4, 4, 16, 16), 120, 300)
    p.drawPath(path)
    p.drawLine(QPointF(12, 3.5), QPointF(12, 12))


def _draw_eye(p: QPainter, c: QColor) -> None:
    _stroked(p, c, 1.7)
    path = QPainterPath()
    path.moveTo(3, 12)
    path.quadTo(12, 3.5, 21, 12)
    path.quadTo(12, 20.5, 3, 12)
    path.closeSubpath()
    p.drawPath(path)
    p.drawEllipse(QPointF(12, 12), 3.2, 3.2)


def _draw_trash(p: QPainter, c: QColor) -> None:
    _stroked(p, c, 1.7)
    p.drawLine(QPointF(4.5, 7), QPointF(19.5, 7))
    p.drawLine(QPointF(10, 4.5), QPointF(14, 4.5))
    path = QPainterPath()
    path.moveTo(6, 7.5)
    path.lineTo(7.2, 20)
    path.lineTo(16.8, 20)
    path.lineTo(18, 7.5)
    p.drawPath(path)
    p.drawLine(QPointF(10, 10), QPointF(10, 17))
    p.drawLine(QPointF(14, 10), QPointF(14, 17))


def _draw_chart(p: QPainter, c: QColor) -> None:
    _filled(p, c)
    p.drawRoundedRect(QRectF(4, 13, 3.2, 7), 1.2, 1.2)
    p.drawRoundedRect(QRectF(10.4, 9, 3.2, 11), 1.2, 1.2)
    p.drawRoundedRect(QRectF(16.8, 5, 3.2, 15), 1.2, 1.2)


def _draw_info(p: QPainter, c: QColor) -> None:
    _stroked(p, c, 1.8)
    p.drawEllipse(QPointF(12, 12), 8.0, 8.0)
    _filled(p, c)
    p.drawEllipse(QPointF(12, 8.2), 1.15, 1.15)
    p.drawRoundedRect(QRectF(10.9, 10.5, 2.2, 7), 1.0, 1.0)


def _draw_window(p: QPainter, c: QColor) -> None:
    _stroked(p, c, 1.7)
    p.drawRoundedRect(QRectF(4, 5, 16, 14), 2.2, 2.2)
    p.drawLine(QPointF(4, 9), QPointF(20, 9))


def _draw_close(p: QPainter, c: QColor) -> None:
    _stroked(p, c, 2.2)
    p.drawLine(QPointF(6, 6), QPointF(18, 18))
    p.drawLine(QPointF(18, 6), QPointF(6, 18))


def _draw_sparkle(p: QPainter, c: QColor) -> None:
    _filled(p, c)
    path = QPainterPath()
    path.moveTo(12, 3)
    path.lineTo(14, 10)
    path.lineTo(21, 12)
    path.lineTo(14, 14)
    path.lineTo(12, 21)
    path.lineTo(10, 14)
    path.lineTo(3, 12)
    path.lineTo(10, 10)
    path.closeSubpath()
    p.drawPath(path)


_REGISTRY: Dict[str, Callable[[QPainter, QColor], None]] = {
    "play": _draw_play,
    "stop": _draw_stop,
    "pause": _draw_pause,
    "lock": _draw_lock,
    "unlock": _draw_unlock,
    "plus": _draw_plus,
    "minus": _draw_minus,
    "settings": _draw_settings,
    "refresh": _draw_refresh,
    "power": _draw_power,
    "eye": _draw_eye,
    "trash": _draw_trash,
    "chart": _draw_chart,
    "info": _draw_info,
    "window": _draw_window,
    "close": _draw_close,
    "sparkle": _draw_sparkle,
}


def available() -> list[str]:
    return sorted(_REGISTRY.keys())


def paint_icon(name: str, size: int = 20, color: str | QColor = "#e7deff") -> QPixmap:
    """把名为 *name* 的矢量图标以指定 *color* 画到 size×size 的 QPixmap 上。"""
    drawer = _REGISTRY.get(name)
    pm = _new_canvas(size)
    if drawer is None:
        return pm
    c = QColor(color) if not isinstance(color, QColor) else color
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    # 缩放 24 -> size
    p.scale(size / 24.0, size / 24.0)
    drawer(p, c)
    p.end()
    return pm


def get_icon(name: str, size: int = 20, color: str | QColor = "#e7deff") -> QIcon:
    """返回一个按需渲染的 QIcon，包含 1x 与 2x 位图。"""
    icon = QIcon()
    for s in (size, size * 2):
        icon.addPixmap(paint_icon(name, s, color))
    return icon


def icon_size(px: int = 18) -> QSize:
    return QSize(px, px)
