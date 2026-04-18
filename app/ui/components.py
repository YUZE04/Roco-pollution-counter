"""UI Skills —— 可复用的"设计组件"。

提供与 ``theme`` 设计 token 一致的高阶 widget：

* :class:`Card` ——带圆角/描边/内边距的内容容器
* :class:`SectionHeader` ——图标 + 标题 + 可选副标题
* :class:`StatTile` ——大数字 + 说明的统计块
* :class:`IconButton` ——带矢量图标 + 可选文字的按钮
* :class:`Pill` ——状态小徽章（带圆点）
* :class:`Divider` ——细分隔线
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from . import theme
from .icons import get_icon, icon_size


# ---------------------------------------------------------------- Card

class Card(QFrame):
    """带圆角、柔和描边的内容容器。"""

    def __init__(self, parent: Optional[QWidget] = None, *, padding: int = 14, radius: int = 12):
        super().__init__(parent)
        self.setObjectName("Card")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            f"#Card {{"
            f"  background-color: {theme.BG_PANEL};"
            f"  border: 1px solid {theme.BG_ELEV};"
            f"  border-radius: {radius}px;"
            f"}}"
            f"#Card:hover {{"
            f"  border: 1px solid {theme.BG_ACCENT};"
            f"}}"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(padding, padding, padding, padding)
        lay.setSpacing(8)
        self._layout = lay

    def body(self) -> QVBoxLayout:
        return self._layout

    def add(self, w: QWidget) -> None:
        self._layout.addWidget(w)


# ---------------------------------------------------------------- SectionHeader

class SectionHeader(QWidget):
    """图标 + 标题 + 副标题的分节头。"""

    def __init__(
        self,
        title: str,
        *,
        icon: Optional[str] = None,
        subtitle: str = "",
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)

        if icon:
            ico = QLabel()
            ico.setPixmap(get_icon(icon, size=18, color=theme.FG_SPECIES).pixmap(18, 18))
            ico.setFixedSize(22, 22)
            ico.setAlignment(Qt.AlignmentFlag.AlignCenter)
            row.addWidget(ico)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(2)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(
            f"color:{theme.FG_TEXT};font-size:12pt;font-weight:600;background:transparent;"
        )
        text_col.addWidget(title_lbl)

        if subtitle:
            sub_lbl = QLabel(subtitle)
            sub_lbl.setStyleSheet(f"color:{theme.FG_DIM};font-size:9pt;background:transparent;")
            text_col.addWidget(sub_lbl)

        row.addLayout(text_col, 1)


# ---------------------------------------------------------------- StatTile

class StatTile(Card):
    """紧凑指标卡：左侧图标 + 右侧(标题 + 大数字)。"""

    def __init__(
        self,
        label: str,
        value: str = "0",
        *,
        icon: Optional[str] = None,
        accent: str = theme.FG_COUNT,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent, padding=14, radius=12)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(84)

        # 清空默认 VBox，换成横向布局
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(14)
        self._layout.addLayout(row)

        # 左：图标圆形徽标
        if icon:
            badge = QLabel()
            badge.setFixedSize(40, 40)
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge.setPixmap(get_icon(icon, size=20, color=accent).pixmap(20, 20))
            badge.setStyleSheet(
                f"background-color: rgba(138, 85, 255, 30);"
                f"border-radius: 20px;"
            )
            row.addWidget(badge, 0, Qt.AlignmentFlag.AlignVCenter)

        # 右：标题 + 数字
        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(2)

        self.lbl_caption = QLabel(label)
        self.lbl_caption.setStyleSheet(
            f"color:{theme.FG_DIM};font-size:9pt;background:transparent;"
            f"font-weight:500;"
        )
        col.addWidget(self.lbl_caption)

        self.lbl_value = QLabel(value)
        self.lbl_value.setStyleSheet(
            f"color:{accent};font-size:22pt;font-weight:700;background:transparent;"
            f"letter-spacing:-0.5px;"
        )
        self.lbl_value.setMinimumHeight(34)
        # tabular-nums：让 0-9 等宽，数字跳动时不会抖
        vf = self.lbl_value.font()
        try:
            vf.setFeature("tnum", 1)
        except Exception:
            pass
        self.lbl_value.setFont(vf)
        col.addWidget(self.lbl_value)

        row.addLayout(col, 1)

    def set_value(self, text: str) -> None:
        self.lbl_value.setText(text)


# ---------------------------------------------------------------- IconButton

class IconButton(QPushButton):
    """带矢量图标的按钮，可选主按钮样式 (``primary=True``)。"""

    def __init__(
        self,
        text: str = "",
        *,
        icon: Optional[str] = None,
        primary: bool = False,
        danger: bool = False,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(text, parent)
        self._icon_name = icon
        self._primary = primary
        self._danger = danger
        if icon:
            if primary:
                color = "#ffffff"
            elif danger:
                color = theme.FG_DANGER
            else:
                color = theme.FG_TEXT
            self.setIcon(get_icon(icon, size=16, color=color))
            self.setIconSize(icon_size(16))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if primary:
            self.setProperty("variant", "primary")
        elif danger:
            self.setProperty("variant", "danger")
        self.setMinimumHeight(32)

    def set_icon_name(self, name: str) -> None:
        self._icon_name = name
        color = "#ffffff" if (self._primary or self._danger) else theme.FG_TEXT
        self.setIcon(get_icon(name, size=16, color=color))


# ---------------------------------------------------------------- Pill

class Pill(QLabel):
    """圆角徽章 + 前置状态色点。"""

    def __init__(self, text: str, *, color: str = theme.FG_DIM, parent: Optional[QWidget] = None):
        super().__init__(text, parent)
        self._apply(color, text)

    def _apply(self, color: str, text: str) -> None:
        c = QColor(color)
        self.setStyleSheet(
            f"QLabel{{"
            f"  color:{color};"
            f"  background:rgba({c.red()},{c.green()},{c.blue()},60);"
            f"  border:1px solid rgba({c.red()},{c.green()},{c.blue()},160);"
            f"  border-radius:10px;"
            f"  padding:3px 12px;"
            f"  font-size:9pt;"
            f"  font-weight:600;"
            f"}}"
        )
        self.setText(text)

    def set_state(self, text: str, color: str) -> None:
        self._apply(color, text)


# ---------------------------------------------------------------- Divider

class Divider(QFrame):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.HLine)
        self.setStyleSheet(f"color:{theme.BORDER};background:{theme.BORDER};max-height:1px;")
