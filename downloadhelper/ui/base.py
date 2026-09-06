"""无边框窗口基础组件：自定义标题栏、阴影容器、可拖拽移动。"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QSize, Qt
from PySide6.QtGui import QColor, QMouseEvent
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QSizeGrip,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .icons import get_icon
from .theme import COLORS

SHADOW_MARGIN = 10


class TitleBarButton(QToolButton):
    """标题栏按钮，悬停时改变图标颜色。"""

    def __init__(self, icon_name: str, tooltip: str = "", color: str = COLORS["muted"],
                 hover_color: str = COLORS["text"], hover_bg: str = None, parent=None):
        super().__init__(parent)
        self._icon_name = icon_name
        self._color = color
        self._hover_color = hover_color
        self.setIcon(get_icon(icon_name, color, 16))
        self.setIconSize(QSize(16, 16))
        self.setToolTip(tooltip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(34, 28)
        if hover_bg:
            self.setObjectName("CloseButton")

    def enterEvent(self, event):
        self.setIcon(get_icon(self._icon_name, self._hover_color, 16))
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.setIcon(get_icon(self._icon_name, self._color, 16))
        super().leaveEvent(event)

    def set_icon_name(self, name: str):
        self._icon_name = name
        self.setIcon(get_icon(name, self._color, 16))


class TitleBar(QFrame):
    """可拖动、可双击最大化的标题栏。"""

    def __init__(self, parent, title: str, subtitle: str = "", icon_name: str = "download",
                 show_buttons: bool = True):
        super().__init__(parent)
        self.setObjectName("TitleBar")
        self.setFixedHeight(52)
        self._window = parent

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 8, 0)
        layout.setSpacing(10)

        icon_label = QLabel()
        icon_label.setPixmap(get_icon(icon_name, COLORS["accent"], 20).pixmap(20, 20))
        layout.addWidget(icon_label)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(0)
        title_label = QLabel(title)
        title_label.setObjectName("AppTitle")
        text_layout.addWidget(title_label)
        if subtitle:
            sub = QLabel(subtitle)
            sub.setObjectName("AppSubtitle")
            text_layout.addWidget(sub)
        layout.addLayout(text_layout)
        layout.addStretch(1)

        if show_buttons:
            self.btn_min = TitleBarButton("minimize", "最小化")
            self.btn_max = TitleBarButton("maximize", "最大化")
            self.btn_close = TitleBarButton("close", "关闭", hover_bg=True)
            self.btn_min.clicked.connect(self._window.showMinimized)
            self.btn_max.clicked.connect(self._toggle_maximize)
            self.btn_close.clicked.connect(self._window.close)
            for btn in (self.btn_min, self.btn_max, self.btn_close):
                layout.addWidget(btn)

    def _toggle_maximize(self):
        window = self._window
        if window.isMaximized():
            window.showNormal()
        else:
            window.showMaximized()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            handle = self._window.windowHandle()
            if handle is not None:
                handle.startSystemMove()
                return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._toggle_maximize()
        super().mouseDoubleClickEvent(event)


class _FramelessMixin:
    """提供圆角阴影容器与最大化时的边距自适应。"""

    def _init_container(self):
        outer = QWidget()
        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(SHADOW_MARGIN, SHADOW_MARGIN, SHADOW_MARGIN, SHADOW_MARGIN)
        outer_layout.setSpacing(0)

        container = QWidget()
        container.setObjectName("AppContainer")
        shadow = QGraphicsDropShadowEffect(container)
        shadow.setBlurRadius(26)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(0, 0, 0, 170))
        container.setGraphicsEffect(shadow)
        outer_layout.addWidget(container)

        content_layout = QVBoxLayout(container)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        self._outer_layout = outer_layout
        self._shadow = shadow
        self.container = container
        self.content_layout = content_layout
        return outer

    def _update_window_state(self):
        maximized = bool(self.windowState() & Qt.WindowState.WindowMaximized)
        margin = 0 if maximized else SHADOW_MARGIN
        self._outer_layout.setContentsMargins(margin, margin, margin, margin)
        self._shadow.setEnabled(not maximized)


class FramelessWindow(QMainWindow, _FramelessMixin):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setCentralWidget(self._init_container())

    def changeEvent(self, event: QEvent):
        super().changeEvent(event)
        if event.type() in (QEvent.Type.WindowStateChange,):
            self._update_window_state()


class FramelessDialog(QDialog, _FramelessMixin):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._init_container())


def add_size_grip(layout):
    """在右下角加入系统尺寸手柄，方便无边框窗口缩放。"""
    grip = QSizeGrip(None)
    grip.setFixedSize(16, 16)
    layout.addWidget(grip, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)
    return grip
