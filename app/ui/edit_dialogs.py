"""统计修改对话框。

* :func:`edit_count_dialog` ——修改单条（精灵名 + 数量）记录的通用对话框，
  用于"今日精灵"、"历史累计"。支持新增/修改/删除。
* :func:`edit_daily_dialog` ——修改某一天的总数，用于"每日总数"表。
"""

from __future__ import annotations

import re
from typing import Optional, Tuple

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from . import theme
from .components import IconButton


_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class _BaseDialog(QDialog):
    def __init__(self, title: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(320)
        self.setStyleSheet(
            f"QDialog{{background-color:{theme.BG_DEEP};}}"
            f"QLabel{{background:transparent;color:{theme.FG_TEXT};}}"
        )


# ---------------- 精灵条目编辑 ----------------

def edit_count_dialog(
    parent: QWidget,
    *,
    title: str,
    name: str = "",
    value: int = 0,
    name_locked: bool = False,
    allow_delete: bool = True,
) -> Optional[Tuple[str, int, bool]]:
    """弹出"精灵 + 次数"编辑对话框。

    返回 ``(name, value, deleted)`` 或 ``None``（用户取消）。
    * ``deleted=True`` 表示用户点了删除按钮（调用方应把该条目的值置 0）。
    * ``name_locked`` 时不可修改精灵名（用于编辑现有行）。
    """
    dlg = _BaseDialog(title, parent)

    form = QFormLayout()
    form.setContentsMargins(16, 16, 16, 8)
    form.setSpacing(10)

    le_name = QLineEdit(name)
    le_name.setPlaceholderText("精灵名（中文）")
    if name_locked:
        le_name.setReadOnly(True)
        le_name.setStyleSheet(f"color:{theme.FG_DIM};")
    form.addRow("精灵:", le_name)

    sp_val = QSpinBox()
    sp_val.setRange(0, 9999999)
    sp_val.setValue(int(value))
    sp_val.setSuffix("  次")
    form.addRow("次数:", sp_val)

    hint = QLabel("次数 = 0 表示删除该条目")
    hint.setStyleSheet(f"color:{theme.FG_HINT};font-size:9pt;")
    form.addRow(hint)

    root = QVBoxLayout(dlg)
    root.addLayout(form)

    # 按钮：删除（可选） + 取消 + 确定
    btn_row = QHBoxLayout()
    btn_row.setContentsMargins(16, 0, 16, 12)

    deleted_flag = {"v": False}
    if allow_delete and name_locked:
        btn_del = IconButton("删除该条", icon="trash", danger=True, parent=dlg)

        def _do_delete():
            if QMessageBox.question(
                dlg, "确认删除", f"确定删除 [{name}] 吗？"
            ) == QMessageBox.StandardButton.Yes:
                deleted_flag["v"] = True
                dlg.accept()

        btn_del.clicked.connect(_do_delete)
        btn_row.addWidget(btn_del)
    btn_row.addStretch(1)

    bb = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
    )
    bb.button(QDialogButtonBox.StandardButton.Ok).setText("保存")
    bb.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
    bb.accepted.connect(dlg.accept)
    bb.rejected.connect(dlg.reject)
    btn_row.addWidget(bb)
    root.addLayout(btn_row)

    sp_val.setFocus()

    if dlg.exec() != QDialog.DialogCode.Accepted:
        return None

    new_name = le_name.text().strip()
    new_val = int(sp_val.value())
    if not new_name:
        QMessageBox.warning(parent, "无效输入", "精灵名不能为空")
        return None
    if new_name == "未识别":
        QMessageBox.warning(parent, "无效名称", "不能使用 '未识别' 作为精灵名")
        return None
    return new_name, new_val, deleted_flag["v"]


# ---------------- 每日总数编辑 ----------------

def edit_daily_dialog(
    parent: QWidget,
    *,
    title: str,
    day: str = "",
    value: int = 0,
    day_locked: bool = False,
) -> Optional[Tuple[str, int]]:
    """弹出"日期 + 总数"编辑对话框。返回 ``(day, value)`` 或 ``None``。"""
    dlg = _BaseDialog(title, parent)

    form = QFormLayout()
    form.setContentsMargins(16, 16, 16, 8)
    form.setSpacing(10)

    le_day = QLineEdit(day)
    le_day.setPlaceholderText("YYYY-MM-DD")
    if day_locked:
        le_day.setReadOnly(True)
        le_day.setStyleSheet(f"color:{theme.FG_DIM};")
    form.addRow("日期:", le_day)

    sp_val = QSpinBox()
    sp_val.setRange(0, 9999999)
    sp_val.setValue(int(value))
    sp_val.setSuffix("  次")
    form.addRow("总数:", sp_val)

    hint = QLabel("注意：修改每日总数不会自动调整当天各精灵明细")
    hint.setStyleSheet(f"color:{theme.FG_HINT};font-size:9pt;")
    hint.setWordWrap(True)
    form.addRow(hint)

    root = QVBoxLayout(dlg)
    root.addLayout(form)

    bb = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
    )
    bb.button(QDialogButtonBox.StandardButton.Ok).setText("保存")
    bb.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
    bb.accepted.connect(dlg.accept)
    bb.rejected.connect(dlg.reject)

    btn_wrap = QHBoxLayout()
    btn_wrap.setContentsMargins(16, 0, 16, 12)
    btn_wrap.addStretch(1)
    btn_wrap.addWidget(bb)
    root.addLayout(btn_wrap)

    sp_val.setFocus()

    if dlg.exec() != QDialog.DialogCode.Accepted:
        return None

    new_day = le_day.text().strip()
    if not _DATE_RE.match(new_day):
        QMessageBox.warning(parent, "日期格式错误", "请使用 YYYY-MM-DD 格式，例如 2025-04-18")
        return None
    return new_day, int(sp_val.value())
