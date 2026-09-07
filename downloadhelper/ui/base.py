"""无边框窗口基础组件：自定义标题栏、阴影容器、可拖拽移动。"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QRect, QSize, Qt, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import (
    QColor,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QBrush,
)
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGraphicsBlurEffect,
    QGraphicsDropShadowEffect,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QSizeGrip,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .icons import get_icon
from .theme import COLORS, get_theme

SHADOW_MARGIN = 10
WINDOW_RADIUS = 14


def _blur_pixmap(pixmap: QPixmap, radius: int) -> QPixmap:
    """对 QPixmap 做带边缘扩展的高斯模糊，避免裁剪边缘透明。"""
    if radius <= 0 or pixmap.isNull():
        return pixmap
    pad = max(2, int(radius * 1.5))
    scene = QGraphicsScene()
    scene.setSceneRect(0, 0, pixmap.width() + pad * 2, pixmap.height() + pad * 2)
    item = QGraphicsPixmapItem(pixmap)
    item.setPos(pad, pad)
    effect = QGraphicsBlurEffect()
    effect.setBlurRadius(float(radius))
    item.setGraphicsEffect(effect)
    scene.addItem(item)
    result = QPixmap(pixmap.width() + pad * 2, pixmap.height() + pad * 2)
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    scene.render(painter, target=QRect(0, 0, result.width(), result.height()),
                 source=scene.sceneRect())
    painter.end()
    return result


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

    def refresh_theme(self, muted: str = None, text: str = None):
        """主题切换后按新配色重绘图标。"""
        self._color = muted or COLORS["muted"]
        self._hover_color = text or COLORS["text"]
        self.setIcon(get_icon(self._icon_name, self._color, 16))


class TitleBar(QFrame):
    """可拖动、可双击最大化的标题栏。"""

    def __init__(self, parent, title: str, subtitle: str = "", icon_name: str = "download",
                 show_buttons: bool = True):
        super().__init__(parent)
        self.setObjectName("TitleBar")
        self.setFixedHeight(52)
        self._window = parent
        self._icon_name = icon_name

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

    def refresh_icons(self):
        """主题切换后刷新标题栏图标配色。"""
        for button in self.findChildren(TitleBarButton):
            button.refresh_theme()
        icon_label = self.findChild(QLabel)
        if icon_label is not None:
            icon_label.setPixmap(
                get_icon(self._icon_name, COLORS["accent"], 20).pixmap(20, 20)
            )

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


class Backdrop(QWidget):
    """窗口底板：绘制主题背景色，或按比例铺满的自定义背景图（支持高斯模糊）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._pixmap = QPixmap()
        self._source_pixmap = QPixmap()
        self._image = ""
        self._alpha = 0.55
        self._blur = 0
        self._pixmap_key = None

    def refresh_theme(self):
        theme = get_theme()
        image = theme.background_image if theme.has_background else ""
        alpha = theme.background_alpha
        blur = theme.background_blur
        key = (image, blur, self.size().width(), self.size().height())
        self._image = image
        self._alpha = alpha
        self._blur = blur
        if key != self._pixmap_key:
            self._pixmap_key = key
            if image:
                source = QPixmap(image)
                if source.isNull():
                    self._source_pixmap = QPixmap()
                    self._pixmap = QPixmap()
                else:
                    self._source_pixmap = source
                    self._pixmap = _blur_pixmap(source, blur) if blur > 0 else source
            else:
                self._source_pixmap = QPixmap()
                self._pixmap = QPixmap()
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        rect = self.rect()
        radius = WINDOW_RADIUS
        path = QPainterPath()
        path.addRoundedRect(rect.x(), rect.y(), rect.width(), rect.height(), radius, radius)
        # 裁剪到圆角矩形，使窗口四角真正圆角
        painter.setClipPath(path)

        base = QColor(COLORS.get("bg", "#0F1420"))
        painter.fillRect(rect, base)

        if not self._pixmap.isNull():
            # 额外留出模糊半径的余量，避免边缘出现透明边
            pad = self._blur
            target = QSize(rect.width() + 2 * pad, rect.height() + 2 * pad)
            scaled = self._pixmap.scaled(
                target,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = int((rect.width() - scaled.width()) / 2)
            y = int((rect.height() - scaled.height()) / 2)
            painter.setOpacity(self._alpha)
            painter.drawPixmap(x, y, scaled)
            painter.setOpacity(1.0)
            # 叠加一层底色，保证文字与控件的可读性
            overlay = QColor(base)
            overlay.setAlphaF(0.15 + 0.5 * (1.0 - self._alpha))
            painter.fillRect(rect, overlay)

        # 圆角描边，强化边缘
        border = QColor(COLORS.get("border", "#2A3350"))
        pen = QPen(border)
        pen.setWidth(1)
        painter.setPen(pen)
        painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        painter.drawPath(path)
        painter.end()


class _FramelessMixin:
    """提供圆角阴影容器与最大化时的边距自适应。"""

    def _init_container(self):
        outer = QWidget()
        outer.setObjectName("ShadowOuter")
        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(SHADOW_MARGIN, SHADOW_MARGIN, SHADOW_MARGIN, SHADOW_MARGIN)
        outer_layout.setSpacing(0)

        container = Backdrop()
        container.setObjectName("AppContainer")
        shadow = QGraphicsDropShadowEffect(container)
        shadow.setBlurRadius(26)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(0, 0, 0, 170))
        container.setGraphicsEffect(shadow)
        outer_layout.addWidget(container)
        get_theme().register(container)

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
        self._closing = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._init_container())

    # ------------------------------------------------------------------ 动画
    def _scaled_geometry(self, geo: QRect, factor: float) -> QRect:
        w = int(geo.width() * factor)
        h = int(geo.height() * factor)
        return QRect(
            geo.x() + (geo.width() - w) // 2,
            geo.y() + (geo.height() - h) // 2,
            w,
            h,
        )

    def showEvent(self, event):
        super().showEvent(event)
        self._animate_in()

    def _animate_in(self):
        geo = self.geometry()
        if not geo.isValid() or geo.width() <= 0:
            return
        start = self._scaled_geometry(geo, 0.94)
        self.setGeometry(start)
        self.setWindowOpacity(0.0)
        self._anim_geo = QPropertyAnimation(self, b"geometry")
        self._anim_geo.setDuration(170)
        self._anim_geo.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim_geo.setStartValue(start)
        self._anim_geo.setEndValue(geo)
        self._anim_opa = QPropertyAnimation(self, b"windowOpacity")
        self._anim_opa.setDuration(170)
        self._anim_opa.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim_opa.setStartValue(0.0)
        self._anim_opa.setEndValue(1.0)
        self._anim_geo.start()
        self._anim_opa.start()

    def _start_close(self, result):
        if self._closing:
            return
        self._closing = True
        geo = self.geometry()
        end = self._scaled_geometry(geo, 0.94)
        self._anim_geo = QPropertyAnimation(self, b"geometry")
        self._anim_geo.setDuration(140)
        self._anim_geo.setEasingCurve(QEasingCurve.Type.InCubic)
        self._anim_geo.setStartValue(geo)
        self._anim_geo.setEndValue(end)
        self._anim_opa = QPropertyAnimation(self, b"windowOpacity")
        self._anim_opa.setDuration(140)
        self._anim_opa.setEasingCurve(QEasingCurve.Type.InCubic)
        self._anim_opa.setStartValue(1.0)
        self._anim_opa.setEndValue(0.0)
        self._anim_opa.finished.connect(lambda: self.done(result))
        self._anim_geo.start()
        self._anim_opa.start()

    def accept(self):
        self._start_close(QDialog.DialogCode.Accepted)

    def reject(self):
        self._start_close(QDialog.DialogCode.Rejected)

    def closeEvent(self, event):
        if self._closing:
            event.accept()
            return
        event.ignore()
        self.reject()


def add_size_grip(layout):
    """在右下角加入系统尺寸手柄，方便无边框窗口缩放。"""
    grip = QSizeGrip(None)
    grip.setFixedSize(16, 16)
    layout.addWidget(grip, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)
    return grip
