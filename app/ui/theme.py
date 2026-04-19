"""设计 Token + 全局 QSS。

本文件是项目的"单一视觉来源 (single source of truth)"：
* 颜色、间距、圆角、时长等 token 以模块常量形式暴露；
* ``qss_main_window()`` 根据 token 生成整站 QSS；
* 其他组件 (``components.py`` / ``icons.py``) 通过引用 token 保持风格一致。
"""

# ---------- Core palette ----------
# 主色：深紫黑底 + 荧光紫强调，延续旧版风格
BG_DEEP = "#171021"
BG_PANEL = "#1f1631"
BG_TITLE = "#231738"
BG_ELEV = "#261a3d"          # 更高一层的浮起面（hover/selected）
BG_ACCENT = "#6633cc"
BG_ACCENT_HI = "#8a55ff"     # 主按钮渐变的高亮端
FG_TEXT = "#e7deff"
FG_DIM = "#a191d6"
FG_HINT = "#7a6aa7"
FG_COUNT = "#ffffff"
FG_SPECIES = "#ffd166"
FG_WARNING = "#ffd166"
FG_SUCCESS = "#40d67a"
FG_DANGER = "#ff6b8a"
BORDER = "#3a2a5c"
BORDER_STRONG = "#5a3e92"
FOCUS_RING = "#8a55ff"

# ---------- Spacing / radius / motion tokens ----------
SPACE_XS = 4
SPACE_SM = 8
SPACE_MD = 12
SPACE_LG = 16
SPACE_XL = 24

RADIUS_SM = 6
RADIUS_MD = 10
RADIUS_LG = 14
RADIUS_PILL = 999

DURATION_FAST = 140
DURATION_BASE = 220
DURATION_SLOW = 360

# 悬浮窗：半透明紫黑，突出计数
OVERLAY_BG_RGBA = (23, 16, 33, 210)  # 带 alpha
OVERLAY_BORDER_RGBA = (102, 51, 204, 150)

FONT_FAMILY = "Microsoft YaHei UI"

FONT_BIG_COUNT = (FONT_FAMILY, 36, True)
FONT_MEDIUM = (FONT_FAMILY, 12, False)
FONT_SMALL = (FONT_FAMILY, 10, False)
FONT_TINY = (FONT_FAMILY, 9, False)


def qss_main_window():
    return f"""
    /* 全局：仅设前景色与字体；背景留给容器自己，以便 Mica/Acrylic 穿透 */
    QWidget {{
        color: {FG_TEXT};
        font-family: "{FONT_FAMILY}";
    }}
    QMainWindow {{
        background: transparent;
    }}
    #CentralWidget {{
        background: transparent;
    }}
    QGroupBox {{
        color: {FG_TEXT};
        border: 1px solid {BORDER};
        border-radius: 10px;
        margin-top: 14px;
        padding: 14px 10px 10px 10px;
        font-weight: bold;
        background-color: {BG_PANEL};
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: 12px;
        padding: 0 6px;
        background-color: {BG_PANEL};
        color: {FG_TEXT};
    }}
    QLabel {{
        background: transparent;
        color: {FG_TEXT};
    }}
    QLabel#Dim {{
        color: {FG_DIM};
    }}
    QPushButton {{
        background-color: {BG_PANEL};
        color: {FG_TEXT};
        border: 1px solid {BORDER};
        border-radius: 10px;
        padding: 7px 14px;
        font-weight: 500;
    }}
    QPushButton:hover {{
        background-color: {BG_ELEV};
        border-color: {BORDER_STRONG};
    }}
    QPushButton:pressed {{
        background-color: {BG_TITLE};
    }}
    QPushButton:focus {{
        border: 1px solid {FOCUS_RING};
        outline: none;
    }}
    QPushButton:disabled {{
        color: {FG_HINT};
        border-color: {BORDER};
        background-color: {BG_PANEL};
    }}
    /* 主按钮：渐变 */
    QPushButton[variant="primary"] {{
        background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {BG_ACCENT_HI}, stop:1 {BG_ACCENT});
        color: #ffffff;
        border: 1px solid {BG_ACCENT_HI};
    }}
    QPushButton[variant="primary"]:hover {{
        background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #9c68ff, stop:1 #7340d9);
        border-color: #a682ff;
    }}
    QPushButton[variant="primary"]:pressed {{
        background-color: #4d269e;
    }}
    /* 危险操作：默认幽灵态，hover 才显红 */
    QPushButton[variant="danger"] {{
        background-color: {BG_PANEL};
        color: {FG_DANGER};
        border: 1px solid rgba(255, 107, 138, 80);
    }}
    QPushButton[variant="danger"]:hover {{
        background-color: rgba(255, 107, 138, 30);
        border: 1px solid {FG_DANGER};
        color: #ffb0c0;
    }}
    QPushButton[variant="danger"]:pressed {{
        background-color: rgba(255, 107, 138, 60);
    }}
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
        background-color: {BG_PANEL};
        color: {FG_TEXT};
        border: 1px solid {BORDER};
        border-radius: {RADIUS_SM}px;
        padding: 5px 9px;
        selection-background-color: {BG_ACCENT};
    }}
    QLineEdit:hover, QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover {{
        border-color: {BORDER_STRONG};
    }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
        border: 1px solid {FOCUS_RING};
    }}
    QComboBox QAbstractItemView {{
        background-color: {BG_PANEL};
        color: {FG_TEXT};
        border: 1px solid {BORDER};
        selection-background-color: {BG_ACCENT};
    }}
    QListWidget, QTextEdit, QPlainTextEdit {{
        background-color: {BG_PANEL};
        color: {FG_TEXT};
        border: 1px solid {BORDER};
        border-radius: 6px;
    }}
    /* 表格：无边框，与 Card 融为一体 */
    QTableWidget, QTableView {{
        background-color: transparent;
        alternate-background-color: {BG_ELEV};
        color: {FG_TEXT};
        gridline-color: transparent;
        border: none;
        selection-background-color: rgba(138, 85, 255, 80);
        selection-color: #ffffff;
    }}
    QTableWidget::item, QTableView::item {{
        padding: 6px 8px;
        border: none;
    }}
    QHeaderView {{
        background-color: transparent;
    }}
    QHeaderView::section {{
        background-color: transparent;
        color: {FG_DIM};
        padding: 6px 8px;
        border: none;
        border-bottom: 1px solid {BG_ELEV};
        font-weight: 600;
    }}
    QTableCornerButton::section {{
        background-color: {BG_TITLE};
        border: none;
    }}
    QScrollBar:vertical {{
        background: {BG_PANEL};
        width: 10px;
        margin: 0;
        border: none;
    }}
    QScrollBar::handle:vertical {{
        background: {BG_ACCENT};
        min-height: 24px;
        border-radius: 5px;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
        background: none;
    }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        background: none;
    }}
    QScrollBar:horizontal {{
        background: {BG_PANEL};
        height: 10px;
        margin: 0;
        border: none;
    }}
    QScrollBar::handle:horizontal {{
        background: {BG_ACCENT};
        min-width: 24px;
        border-radius: 5px;
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0;
        background: none;
    }}
    QCheckBox {{
        color: {FG_TEXT};
        background: transparent;
    }}
    QTabWidget::pane {{
        border: 1px solid {BG_ELEV};
        border-radius: {RADIUS_MD}px;
        background-color: {BG_PANEL};
        top: -1px;
    }}
    QTabBar {{
        background: transparent;
        qproperty-drawBase: 0;
    }}
    QTabBar::tab {{
        background-color: transparent;
        color: {FG_DIM};
        padding: 8px 18px;
        border: none;
        border-bottom: 2px solid transparent;
        margin-right: 4px;
        font-weight: 500;
    }}
    QTabBar::tab:selected {{
        color: #ffffff;
        border-bottom: 2px solid {BG_ACCENT_HI};
    }}
    QTabBar::tab:hover:!selected {{
        color: {FG_TEXT};
        border-bottom: 2px solid {BORDER_STRONG};
    }}
    QMenu {{
        background-color: {BG_PANEL};
        color: {FG_TEXT};
        border: 1px solid {BORDER};
    }}
    QMenu::item:selected {{
        background-color: {BG_ACCENT};
    }}
    QMessageBox, QDialog {{
        background-color: {BG_DEEP};
        color: {FG_TEXT};
    }}
    """
