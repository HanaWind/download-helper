"""主题系统：深色 / 浅色 / 跟随时间，以及自定义背景图。

- `PALETTES` 保存深色与浅色两套配色；
- `ThemeManager` 负责根据设置生成 QSS、应用到整个程序，并通知所有窗口重绘背景；
- `Backdrop`（见 `ui.base`）负责绘制纯色或自定义背景图。
"""

from __future__ import annotations

import datetime as _dt
import os
import weakref

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

DARK = {
    "bg": "#0F1420",
    "panel": "#141B29",
    "card": "#1A2133",
    "card_hover": "#1F2739",
    "border": "#242E44",
    "text": "#E6EBF5",
    "muted": "#8A97B1",
    "accent": "#4C8DFF",
    "accent2": "#8B7CFF",
    "success": "#35D399",
    "warn": "#FFB020",
    "danger": "#FF5C5C",
    "title_bg": "#121826",
    "title_border": "#1B2334",
    "input_bg": "#121A29",
    "input_disabled": "#101623",
    "ghost_bg": "#182031",
    "ghost_hover": "#212B41",
    "ghost_border_hover": "#33405C",
    "toolbtn_hover": "#212B41",
    "toolbtn_pressed": "#2A3550",
    "progress_bg": "#131A29",
    "progress_paused": "#5A6480",
    "scroll_handle": "#26314A",
    "scroll_handle_hover": "#33405C",
    "tooltip_bg": "#1B2334",
    "primary_disabled_bg": "#2A3550",
    "primary_disabled_text": "#7C88A3",
    "empty_icon": "#2C3854",
    "text_on_accent": "#FFFFFF",
    "shadow": "rgba(0, 0, 0, 0.66)",
}

LIGHT = {
    "bg": "#EDF1F8",
    "panel": "#FFFFFF",
    "card": "#FFFFFF",
    "card_hover": "#F4F7FD",
    "border": "#DCE3EF",
    "text": "#16203A",
    "muted": "#6B7893",
    "accent": "#2F6FE4",
    "accent2": "#6E63F2",
    "success": "#12A177",
    "warn": "#C97C06",
    "danger": "#D93B54",
    "title_bg": "#FFFFFF",
    "title_border": "#E4EAF5",
    "input_bg": "#FFFFFF",
    "input_disabled": "#F1F4FA",
    "ghost_bg": "#FFFFFF",
    "ghost_hover": "#F1F5FC",
    "ghost_border_hover": "#C2D0E8",
    "toolbtn_hover": "#E7EDF8",
    "toolbtn_pressed": "#D8E2F2",
    "progress_bg": "#E2E8F3",
    "progress_paused": "#9AA7BF",
    "scroll_handle": "#C6D0E2",
    "scroll_handle_hover": "#AEBBD4",
    "tooltip_bg": "#FFFFFF",
    "primary_disabled_bg": "#C9D4E8",
    "primary_disabled_text": "#F7F9FD",
    "empty_icon": "#C3CDDF",
    "text_on_accent": "#FFFFFF",
    "shadow": "rgba(15, 25, 45, 0.35)",
}

PALETTES = {"dark": DARK, "light": LIGHT}

MODES = ("dark", "light", "auto")
MODE_LABELS = {"dark": "深色", "light": "浅色", "auto": "跟随时间（自动）"}

# 跟随时间模式下，白天使用浅色主题的时间段 [7:00, 19:00)
AUTO_DAY_START = 7
AUTO_DAY_END = 19

# 自定义背景图生效时，各层使用半透明色以透出背景
_TRANSLUCENT_ALPHA = {
    "card": 0.84,
    "card_hover": 0.90,
    "panel": 0.80,
    "input_bg": 0.88,
    "input_disabled": 0.80,
    "ghost_bg": 0.84,
    "title_bg": 0.72,
    "progress_bg": 0.55,
    "tooltip_bg": 0.92,
    "scroll_handle": 0.65,
}

#: 当前生效的配色（原地更新，方便各处直接读取）
COLORS = dict(DARK)


def _rgba(color: str, alpha: float) -> str:
    color = color.lstrip("#")
    red, green, blue = (int(color[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({red}, {green}, {blue}, {alpha:.3f})"


def _css(palette: dict, key: str, translucent: bool = False) -> str:
    value = palette.get(key, DARK.get(key, "#000000"))
    if translucent:
        alpha = _TRANSLUCENT_ALPHA.get(key)
        if alpha is not None:
            return _rgba(value, alpha)
    return value


def build_qss(palette: dict, translucent: bool = False) -> str:
    """根据配色生成完整样式表；translucent 表示启用了自定义背景图。"""
    def c(key: str) -> str:
        return _css(palette, key, translucent)

    return f"""
* {{
    color: {c('text')};
    font-family: "Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI", "PingFang SC", sans-serif;
    font-size: 13px;
}}

QWidget#AppContainer {{
    background: transparent;
    border: 1px solid {c('border')};
    border-radius: 14px;
}}

QMainWindow, QDialog, QWidget#ShadowOuter {{ background: transparent; }}

QWidget#TitleBar {{
    background: {c('title_bg')};
    border-top-left-radius: 13px;
    border-top-right-radius: 13px;
    border-bottom: 1px solid {c('title_border')};
}}

QLabel#AppTitle {{
    font-size: 14px;
    font-weight: 600;
    letter-spacing: 0.4px;
}}

QLabel#AppSubtitle {{
    color: {c('muted')};
    font-size: 12px;
}}

QLabel#HeroTitle {{
    font-size: 20px;
    font-weight: 600;
}}

QLabel#HeroSubtitle {{
    color: {c('muted')};
    font-size: 12.5px;
}}

QLabel#Muted {{ color: {c('muted')}; }}
QLabel#Hint {{ color: {c('muted')}; font-size: 12px; }}
QLabel#HintError {{ color: {c('danger')}; font-size: 12px; }}
QLabel#HintOk {{ color: {c('success')}; font-size: 12px; }}

QLineEdit {{
    background: {c('input_bg')};
    border: 1px solid {c('border')};
    border-radius: 10px;
    padding: 9px 14px;
    selection-background-color: {c('accent')};
    selection-color: {c('text_on_accent')};
}}
QLineEdit:focus {{ border: 1px solid {c('accent')}; }}
QLineEdit:disabled {{ color: {c('muted')}; background: {c('input_disabled')}; }}

QPushButton#PrimaryButton {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {c('accent')}, stop:1 {c('accent2')});
    color: {c('text_on_accent')};
    border: none;
    border-radius: 10px;
    padding: 10px 26px;
    font-weight: 600;
}}
QPushButton#PrimaryButton:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {c('accent2')}, stop:1 {c('accent')});
}}
QPushButton#PrimaryButton:pressed {{ background: {c('accent')}; }}
QPushButton#PrimaryButton:disabled {{
    background: {c('primary_disabled_bg')};
    color: {c('primary_disabled_text')};
}}

QPushButton#GhostButton {{
    background: {c('ghost_bg')};
    border: 1px solid {c('border')};
    border-radius: 10px;
    padding: 9px 18px;
    color: {c('text')};
}}
QPushButton#GhostButton:hover {{
    background: {c('ghost_hover')};
    border: 1px solid {c('ghost_border_hover')};
}}

QPushButton#DangerButton {{
    background: {_rgba(palette.get('danger', '#FF5C5C'), 0.16)};
    border: 1px solid {_rgba(palette.get('danger', '#FF5C5C'), 0.42)};
    border-radius: 10px;
    padding: 9px 18px;
    color: {c('danger')};
    font-weight: 600;
}}
QPushButton#DangerButton:hover {{
    background: {_rgba(palette.get('danger', '#FF5C5C'), 0.26)};
}}

QToolButton {{
    background: transparent;
    border: none;
    border-radius: 8px;
    padding: 5px;
}}
QToolButton:hover {{ background: {c('toolbtn_hover')}; }}
QToolButton:pressed {{ background: {c('toolbtn_pressed')}; }}
QToolButton:disabled {{ background: transparent; }}
QToolButton#CloseButton:hover {{ background: #E0455C; }}
QToolButton#IconButton {{
    background: {c('ghost_bg')};
    border: 1px solid {c('border')};
}}

QFrame#Card {{
    background: {c('card')};
    border: 1px solid {c('border')};
    border-radius: 12px;
}}
QFrame#Card:hover {{ background: {c('card_hover')}; }}

QProgressBar {{
    background: {c('progress_bg')};
    border: none;
    border-radius: 5px;
    height: 8px;
    max-height: 8px;
}}
QProgressBar::chunk {{
    border-radius: 5px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {c('accent')}, stop:1 {c('accent2')});
}}
QProgressBar[state="paused"]::chunk {{ background: {c('progress_paused')}; }}
QProgressBar[state="error"]::chunk {{ background: {c('danger')}; }}
QProgressBar[state="finished"]::chunk {{ background: {c('success')}; }}

QAbstractScrollArea {{ background: transparent; border: none; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QWidget#qt_scrollarea_viewport {{ background: transparent; }}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 4px 2px 4px 0;
}}
QScrollBar::handle:vertical {{
    background: {c('scroll_handle')};
    border-radius: 5px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: {c('scroll_handle_hover')}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
QScrollBar:horizontal {{ height: 0; }}

QSpinBox {{
    background: {c('input_bg')};
    border: 1px solid {c('border')};
    border-radius: 8px;
    padding: 6px 8px;
    min-width: 90px;
}}
QSpinBox::up-button, QSpinBox::down-button {{ width: 18px; background: transparent; }}

QComboBox {{
    background: {c('input_bg')};
    border: 1px solid {c('border')};
    border-radius: 8px;
    padding: 7px 10px;
    min-width: 150px;
}}
QComboBox:hover {{ border: 1px solid {c('accent')}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background: {c('panel')};
    border: 1px solid {c('border')};
    selection-background-color: {c('accent')};
    selection-color: {c('text_on_accent')};
    color: {c('text')};
    outline: none;
}}

QSlider::groove:horizontal {{
    height: 4px;
    background: {c('progress_bg')};
    border-radius: 2px;
}}
QSlider::sub-page:horizontal {{ background: {c('accent')}; border-radius: 2px; }}
QSlider::handle:horizontal {{
    width: 14px;
    margin: -5px 0;
    border-radius: 7px;
    background: {c('accent')};
}}

QGroupBox {{
    border: 1px solid {c('border')};
    border-radius: 10px;
    margin-top: 16px;
    padding: 16px 12px 10px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: {c('muted')};
}}

QToolTip {{
    background: {c('tooltip_bg')};
    color: {c('text')};
    border: 1px solid {c('border')};
    padding: 5px 8px;
}}

QWidget#EmptyState {{ background: transparent; }}
QWidget#EmptyState QLabel {{ color: {c('muted')}; }}

QMessageBox {{
    background: {c('panel')};
}}
QMessageBox QLabel {{ color: {c('text')}; }}
QMessageBox QPushButton {{
    background: {c('ghost_bg')};
    border: 1px solid {c('border')};
    border-radius: 8px;
    padding: 6px 18px;
    color: {c('text')};
    min-width: 70px;
}}
"""


class ThemeManager(QObject):
    """主题管理：模式、背景图与应用。"""

    themeChanged = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.mode = "dark"          # dark / light / auto
        self.background_image = ""
        self.background_opacity = 55  # 0 ~ 100
        self._background_blur = 0     # 高斯模糊半径（像素），0 表示不模糊
        self._surfaces = weakref.WeakSet()
        self._applied_mode = None

    # ------------------------------------------------------------------ 配置
    def configure(self, mode: str = None, image: str = None, opacity: int = None,
                  blur: int = None):
        if mode is not None:
            self.mode = mode if mode in MODES else "dark"
        if image is not None:
            self.background_image = image or ""
        if opacity is not None:
            self.background_opacity = max(0, min(100, int(opacity)))
        if blur is not None:
            self._background_blur = max(0, min(40, int(blur)))

    def set_mode(self, mode: str):
        self.configure(mode=mode)

    # ------------------------------------------------------------------ 解析
    def resolved_mode(self) -> str:
        """auto 模式下按当前时间解析：7:00-19:00 为浅色，其余为深色。"""
        if self.mode != "auto":
            return self.mode if self.mode in PALETTES else "dark"
        hour = _dt.datetime.now().hour
        return "light" if AUTO_DAY_START <= hour < AUTO_DAY_END else "dark"

    @property
    def resolved_label(self) -> str:
        return MODE_LABELS.get(self.resolved_mode(), self.resolved_mode())

    def palette(self) -> dict:
        return dict(PALETTES.get(self.resolved_mode(), DARK))

    @property
    def has_background(self) -> bool:
        return bool(self.background_image) and os.path.isfile(self.background_image)

    @property
    def background_alpha(self) -> float:
        return max(0.0, min(1.0, self.background_opacity / 100.0))

    @property
    def background_blur(self) -> int:
        return self._background_blur

    # ------------------------------------------------------------------ 应用
    def register(self, surface):
        self._surfaces.add(surface)
        # 新注册的界面立即按当前主题刷新（含背景图/模糊），确保启动时即生效
        if hasattr(surface, "refresh_theme"):
            surface.refresh_theme()

    def apply(self, app=None) -> str:
        """生成并应用样式表，返回当前解析出的模式。"""
        global QSS

        palette = self.palette()
        COLORS.clear()
        COLORS.update(palette)
        QSS = build_qss(palette, translucent=self.has_background)

        target = app or QApplication.instance()
        if target is not None:
            target.setStyleSheet(QSS)

        for surface in list(self._surfaces):
            try:
                surface.refresh_theme()
            except RuntimeError:  # 对象已被销毁
                continue

        mode = self.resolved_mode()
        self._applied_mode = mode
        self.themeChanged.emit(mode)
        return mode

    def refresh_if_needed(self) -> bool:
        """跟随时间模式下检查是否需要切换，返回是否发生了变化。"""
        if self.mode != "auto" and self._applied_mode is not None:
            return False
        if self._applied_mode == self.resolved_mode():
            return False
        self.apply()
        return True


_theme: ThemeManager = None


def get_theme() -> ThemeManager:
    """全局主题管理器（懒加载）。"""
    global _theme
    if _theme is None:
        _theme = ThemeManager()
    return _theme


#: 当前生效的样式表（由 ThemeManager.apply 更新）
QSS = build_qss(DARK)
