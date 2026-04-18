"""在整屏上短暂显示检测窗口的半透明浮层，用于校准区域。"""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPen
from PyQt6.QtWidgets import QWidget


class RegionPreview(QWidget):
    def __init__(self, middle: dict, header: dict, name_rel: dict):
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        self._middle = dict(middle or {})
        self._header = dict(header or {})
        self._name_rel = dict(name_rel or {})

        # 覆盖所有屏幕
        geo = None
        for screen in QGuiApplication.screens():
            g = screen.geometry()
            geo = g if geo is None else geo.united(g)
        if geo is not None:
            self.setGeometry(geo)

    def show_for(self, ms: int) -> None:
        self.show()
        QTimer.singleShot(ms, self.close)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        origin_x = self.geometry().x()
        origin_y = self.geometry().y()

        def _draw(region: dict, color: QColor, label: str):
            if not region:
                return
            x = int(region.get("left", 0)) - origin_x
            y = int(region.get("top", 0)) - origin_y
            w = int(region.get("width", 0))
            h = int(region.get("height", 0))
            if w <= 0 or h <= 0:
                return
            fill = QColor(color)
            fill.setAlpha(60)
            painter.fillRect(x, y, w, h, fill)
            pen = QPen(color, 2)
            painter.setPen(pen)
            painter.drawRect(x, y, w, h)
            painter.setFont(QFont("Microsoft YaHei UI", 12, QFont.Weight.Bold))
            painter.drawText(x + 6, y + 18, label)

        # 中间关键字区 —— 绿
        _draw(self._middle, QColor("#40d67a"), "关键字区")
        # 头部区域 —— 橙
        _draw(self._header, QColor("#ffa657"), "头部区")
        # 精灵名实际区域（头部坐标 + 相对偏移）—— 紫
        header_x = int(self._header.get("left", 0))
        header_y = int(self._header.get("top", 0))
        name_abs = {
            "left": header_x + int(self._name_rel.get("left", 0)),
            "top": header_y + int(self._name_rel.get("top", 0)),
            "width": int(self._name_rel.get("width", 0)),
            "height": int(self._name_rel.get("height", 0)),
        }
        _draw(name_abs, QColor("#bc5cff"), "精灵名区")
