"""轻量级 SVG 图标（无需外部资源文件，可任意着色）。"""

from __future__ import annotations

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

_PATHS = {
    "download": "M12 4v11M7.8 10.8L12 15l4.2-4.2M4.5 19.5h15",
    "pause": "M9.5 5v14M14.5 5v14",
    "play": "M8 5.5l10 6.5-10 6.5z",
    "stop": "M7 7h10v10H7z",
    "trash": "M4.5 7h15M9.5 7V4.5h5V7M6.5 7l1 12.5h9L17.5 7M10.5 10.5v6M13.5 10.5v6",
    "folder": (
        "M3.5 7.5A1.5 1.5 0 0 1 5 6h3.6l1.9 2H19a1.5 1.5 0 0 1 1.5 1.5v7"
        "A1.5 1.5 0 0 1 19 18H5a1.5 1.5 0 0 1-1.5-1.5z"
    ),
    "link": (
        "M10.5 13.5a4 4 0 0 0 5.7 0l2.3-2.3a4 4 0 0 0-5.7-5.7l-1.3 1.3"
        "M13.5 10.5a4 4 0 0 0-5.7 0l-2.3 2.3a4 4 0 0 0 5.7 5.7l1.3-1.3"
    ),
    "close": "M6.5 6.5l11 11M17.5 6.5l-11 11",
    "minimize": "M6 12h12",
    "maximize": "M7.5 7.5h9v9h-9z",
    "restore": "M8.5 8.5h10v10h-10zM5.5 5.5h8v3M5.5 5.5v8h3",
    "settings": (
        "M4 8h9M17 8h3M4 16h4M12 16h8"
        "M13 8a2 2 0 1 0 4 0 2 2 0 0 0-4 0M10 16a2 2 0 1 0 4 0 2 2 0 0 0-4 0"
    ),
    "refresh": "M20 12a8 8 0 1 1-2.6-5.9M20 4.5V10h-5.2",
    "check": "M5.5 12.5l4 4 9-9.5",
    "alert": "M12 4.5l8.5 15h-17zM12 10v4M12 16.8h.01",
    "file": "M6.5 3.5h7l4.5 4.5v12a1 1 0 0 1-1 1h-10a1 1 0 0 1-1-1v-16a1 1 0 0 1 1-1zM13 3.5V8h4.5",
    "magnet": "M6 4v8a6 6 0 0 0 12 0V4h-3v8a3 3 0 0 1-6 0V4z",
    "speed": "M4 17a8 8 0 1 1 16 0M12 13l4-4",
    "info": "M12 3.5a8.5 8.5 0 1 0 0 17 8.5 8.5 0 0 0 0-17zM12 11v5.5M12 8h.01",
    "spinner": "M12 4a8 8 0 1 0 8 8",
}

_CACHE: dict = {}


def get_icon(name: str, color: str = "#E6EBF5", size: int = 20,
             stroke_width: float = 1.9, filled: bool = False) -> QIcon:
    """返回指定颜色与尺寸的矢量图标（带缓存）。"""
    key = (name, color, size, stroke_width, filled)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached

    path_data = _PATHS.get(name, _PATHS["file"])
    fill = color if filled else "none"
    stroke = "none" if filled else color
    width = 0 if filled else stroke_width
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 24 24">'
        f'<path d="{path_data}" fill="{fill}" stroke="{stroke}" stroke-width="{width}" '
        f'stroke-linecap="round" stroke-linejoin="round"/></svg>'
    )

    renderer = QSvgRenderer()
    renderer.load(QByteArray(svg.encode("utf-8")))
    ratio = 2
    pixmap = QPixmap(int(size * ratio), int(size * ratio))
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(ratio)
    icon = QIcon(pixmap)
    _CACHE[key] = icon
    return icon


def app_icon(size: int = 64) -> QIcon:
    return get_icon("download", "#4C8DFF", size=size, stroke_width=2.2)
