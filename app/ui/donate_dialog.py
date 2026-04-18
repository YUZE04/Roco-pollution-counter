"""打赏作者对话框。

显示支付宝账号并自动复制到剪贴板。以后如果作者放了收款码图片
(``assets/alipay_qr.png`` / ``assets/wechat_qr.png``)，会自动显示。
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QGuiApplication, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from . import theme
from .components import IconButton


ALIPAY_ACCOUNT = "15206290688"


def _find_qr(*names: str) -> Optional[Path]:
    """在常见路径里找收款码图片。"""
    roots = [
        Path.cwd(),
        Path.cwd() / "assets",
        Path(__file__).resolve().parent.parent.parent,
        Path(__file__).resolve().parent.parent.parent / "assets",
    ]
    for root in roots:
        for name in names:
            p = root / name
            if p.exists():
                return p
    return None


class DonateDialog(QDialog):
    """打赏作者对话框——支付宝账号 + 可选二维码。"""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("打赏作者")
        self.setModal(True)
        self.setMinimumWidth(380)
        self.setStyleSheet(
            f"QDialog{{background-color:{theme.BG_DEEP};}}"
            f"QLabel{{color:{theme.FG_TEXT};background:transparent;}}"
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 16)
        root.setSpacing(12)

        # 标题
        title = QLabel("感谢你的支持 ❤")
        title.setStyleSheet(
            f"color:{theme.FG_SPECIES};font-size:15pt;font-weight:700;"
            f"background:transparent;"
        )
        root.addWidget(title)

        subtitle = QLabel(
            "如果这款工具帮到了你，欢迎请作者喝杯奶茶。\n"
            "所有打赏都会被记住，会变成下一个功能 🙂"
        )
        subtitle.setStyleSheet(
            f"color:{theme.FG_DIM};font-size:10pt;background:transparent;"
        )
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)

        # 二维码（如有）
        qr_path = _find_qr("alipay_qr.png", "donate_qr.png", "打赏.png")
        if qr_path is not None:
            qr_row = QHBoxLayout()
            qr_row.addStretch(1)
            qr_label = QLabel()
            pm = QPixmap(str(qr_path))
            if not pm.isNull():
                pm = pm.scaled(
                    200, 200,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                qr_label.setPixmap(pm)
                qr_label.setStyleSheet(
                    f"padding:8px;border:1px solid {theme.BORDER};"
                    f"background:{theme.BG_PANEL};border-radius:8px;"
                )
            qr_row.addWidget(qr_label)
            qr_row.addStretch(1)
            root.addLayout(qr_row)

        # 账号卡
        acc_label = QLabel("支付宝账号")
        acc_label.setStyleSheet(
            f"color:{theme.FG_DIM};font-size:9pt;background:transparent;"
        )
        root.addWidget(acc_label)

        acc_value = QLabel(ALIPAY_ACCOUNT)
        acc_value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        acc_font = QFont(theme.FONT_FAMILY, 16, QFont.Weight.Bold)
        try:
            acc_font.setFeature("tnum", 1)
        except Exception:
            pass
        acc_value.setFont(acc_font)
        acc_value.setStyleSheet(
            f"color:{theme.FG_COUNT};"
            f"background-color:rgba(138,85,255,30);"
            f"border:1px solid rgba(138,85,255,140);"
            f"border-radius:8px;"
            f"padding:10px 14px;"
            f"letter-spacing:1.5px;"
        )
        root.addWidget(acc_value)

        self._status_label = QLabel("")
        self._status_label.setStyleSheet(
            f"color:{theme.FG_SUCCESS};font-size:9pt;background:transparent;"
        )
        root.addWidget(self._status_label)

        # 按钮
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self.btn_copy = IconButton("复制账号", icon="sparkle", primary=True)
        self.btn_copy.clicked.connect(self._copy_to_clipboard)
        btn_close = IconButton("关闭", icon="close")
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(self.btn_copy)
        btn_row.addStretch(1)
        btn_row.addWidget(btn_close)
        root.addLayout(btn_row)

        # 自动复制一次，给个立即反馈
        self._copy_to_clipboard()

    def _copy_to_clipboard(self) -> None:
        cb = QGuiApplication.clipboard() or QApplication.clipboard()
        if cb is not None:
            cb.setText(ALIPAY_ACCOUNT)
            self._status_label.setText(f"账号已复制到剪贴板：{ALIPAY_ACCOUNT}")
        else:
            self._status_label.setText("")
