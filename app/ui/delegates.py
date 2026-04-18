"""自定义绘制委托与微件。

* :class:`CountBarDelegate` ——在表格的"次数"列里，文字后面画一条占比进度条；
* :class:`SparkLine` ——极简 7 天折线小图，贴在某个区域旁边。
"""

from __future__ import annotations

from typing import List, Optional

from PyQt6.QtCore import QPointF, QRect, QRectF, QSize, Qt
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
)
from PyQt6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem, QWidget

from . import theme


class CountBarDelegate(QStyledItemDelegate):
    """在表格"次数"列背后画一条半透明进度条。

    * 数字会居右；
    * 进度条覆盖整行宽度（或整个单元格宽度），用 row 值 / max 值。
    * ``value_column`` 指定"数字"所在列索引。
    """

    def __init__(
        self,
        *,
        value_column: int = 1,
        bar_color: str = theme.BG_ACCENT,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._col = value_column
        self._bar_color = QColor(bar_color)
        self._max_value = 1

    def set_max_value(self, v: int) -> None:
        self._max_value = max(1, int(v))

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:  # noqa: D401
        # 背景（支持选中/alternate）——让父类先画
        super().paint(painter, option, index)

        if index.column() != self._col:
            return

        try:
            value = int(index.data() or 0)
        except (TypeError, ValueError):
            return

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        ratio = min(1.0, float(value) / float(self._max_value))
        full_rect: QRect = option.rect
        # 进度条占单元格内缩 4px 的矩形底部 5px 高
        bar_h = 4
        inset = 6
        bar_rect = QRectF(
            full_rect.x() + inset,
            full_rect.bottom() - bar_h - 4,
            max(0, full_rect.width() - inset * 2),
            bar_h,
        )
        # 底槽
        painter.setPen(Qt.PenStyle.NoPen)
        trough = QColor(theme.BG_ELEV)
        trough.setAlpha(160)
        painter.setBrush(trough)
        painter.drawRoundedRect(bar_rect, bar_h / 2, bar_h / 2)

        # 实条：紫→青渐变
        fill_w = bar_rect.width() * ratio
        if fill_w >= 1:
            fill_rect = QRectF(bar_rect.x(), bar_rect.y(), fill_w, bar_rect.height())
            grad = QLinearGradient(fill_rect.topLeft(), fill_rect.topRight())
            grad.setColorAt(0.0, QColor(138, 85, 255, 220))
            grad.setColorAt(1.0, QColor(96, 196, 255, 220))
            painter.setBrush(QBrush(grad))
            painter.drawRoundedRect(fill_rect, bar_h / 2, bar_h / 2)

        painter.restore()


class SparkLine(QWidget):
    """贴在 Card 顶部的极简折线图。

    传入 ``values`` 列表按时间升序（最旧 → 最新），内部自动缩放。
    """

    def __init__(
        self,
        values: Optional[List[float]] = None,
        *,
        line_color: str = "#8a55ff",
        fill: bool = True,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._values: List[float] = list(values or [])
        self._line = QColor(line_color)
        self._fill = fill
        self.setMinimumHeight(36)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

    def set_values(self, values: List[float]) -> None:
        self._values = [float(v) for v in values]
        self.update()

    def sizeHint(self) -> QSize:  # noqa: D401
        return QSize(120, 40)

    def paintEvent(self, _event):
        if not self._values:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        rect = self.rect().adjusted(2, 4, -2, -4)
        vmin = min(self._values)
        vmax = max(self._values)
        span = max(1e-6, vmax - vmin)
        n = len(self._values)
        if n == 1:
            xs = [rect.center().x()]
        else:
            xs = [rect.x() + i * rect.width() / (n - 1) for i in range(n)]
        ys = [
            rect.bottom() - (v - vmin) / span * rect.height()
            for v in self._values
        ]

        points = [QPointF(x, y) for x, y in zip(xs, ys)]

        # 填充面积
        if self._fill and n >= 2:
            area = QPainterPath()
            area.moveTo(points[0].x(), rect.bottom())
            for p in points:
                area.lineTo(p)
            area.lineTo(points[-1].x(), rect.bottom())
            area.closeSubpath()
            grad = QLinearGradient(0, rect.top(), 0, rect.bottom())
            grad.setColorAt(0.0, QColor(self._line.red(), self._line.green(), self._line.blue(), 90))
            grad.setColorAt(1.0, QColor(self._line.red(), self._line.green(), self._line.blue(), 0))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(grad))
            painter.drawPath(area)

        # 折线
        pen = QPen(self._line, 1.6)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        line = QPainterPath()
        line.moveTo(points[0])
        for p in points[1:]:
            line.lineTo(p)
        painter.drawPath(line)

        # 最后一个点强调
        last = points[-1]
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._line)
        painter.drawEllipse(last, 2.6, 2.6)
        painter.setBrush(QColor(255, 255, 255, 200))
        painter.drawEllipse(last, 1.1, 1.1)
