"""文件信息确认弹窗：展示文件名、大小、格式与保存位置，确认后才开始下载。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..core.models import KIND_LABELS, FileInfo, LinkKind
from ..core.utils import (
    category_color,
    category_label,
    extension_of,
    format_size,
)
from .base import FramelessDialog, TitleBar
from .icons import get_icon
from .theme import COLORS


def build_badge(name: str, mime: str = "", size: int = 56) -> QLabel:
    color = category_color(name, mime)
    ext = extension_of(name)
    if not ext:
        ext = category_label(name, mime)[:2]
    badge = QLabel(ext.upper()[:4])
    badge.setFixedSize(size, size)
    badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
    badge.setStyleSheet(
        f"background: {color}; border-radius: 14px; color: #0E131F; "
        f"font-size: {int(size * 0.26)}px; font-weight: 700;"
    )
    return badge


class FileInfoDialog(FramelessDialog):
    def __init__(self, info: FileInfo, save_dir: str, threads: int = 8, parent=None):
        super().__init__(parent)
        self.info = info
        self.save_dir = save_dir
        self._confirmed = False

        self.setMinimumWidth(560)
        self.setModal(True)

        title_icon = "magnet" if info.kind in (LinkKind.MAGNET, LinkKind.TORRENT) else "download"
        self.content_layout.addWidget(
            TitleBar(self, "文件信息", "确认信息无误后开始下载", icon_name=title_icon)
        )
        self.content_layout.addWidget(self._build_body())
        self.content_layout.addWidget(self._build_footer())

    # ------------------------------------------------------------------ 界面
    def _build_body(self) -> QWidget:
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(24, 20, 24, 16)
        layout.setSpacing(16)

        header = QHBoxLayout()
        header.setSpacing(14)
        header.addWidget(build_badge(self.info.name, self.info.mime, 58))
        text_layout = QVBoxLayout()
        text_layout.setSpacing(6)
        self.name_edit = QLineEdit(self.info.name)
        self.name_edit.setStyleSheet(
            "font-size: 15px; font-weight: 600; padding: 8px 12px;"
        )
        text_layout.addWidget(self.name_edit)
        source = QLabel(self._source_text())
        source.setObjectName("Muted")
        source.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        source.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        text_layout.addWidget(source)
        header.addLayout(text_layout, 1)
        layout.addLayout(header)

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(10)
        grid.setColumnStretch(1, 1)

        size_text = format_size(self.info.size)
        if self.info.kind in (LinkKind.MAGNET, LinkKind.TORRENT):
            file_count = self.info.extra.get("file_count", 0)
            if file_count:
                size_text += f"（共 {file_count} 个文件）"
        rows = [
            ("文件大小", size_text),
            ("文件格式", self._format_text()),
            ("下载方式", self._method_text()),
            ("保存位置", self.save_dir),
        ]
        self.dir_label = None
        for row, (key, value) in enumerate(rows):
            key_label = QLabel(key)
            key_label.setObjectName("Muted")
            key_label.setFixedWidth(70)
            value_label = QLabel(value)
            value_label.setWordWrap(True)
            value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            if key == "保存位置":
                self.dir_label = value_label
            grid.addWidget(key_label, row, 0)
            grid.addWidget(value_label, row, 1)
            if key == "保存位置":
                browse = QToolButton()
                browse.setObjectName("IconButton")
                browse.setIcon(get_icon("folder", COLORS["text"], 16))
                browse.setCursor(Qt.CursorShape.PointingHandCursor)
                browse.setToolTip("选择保存目录")
                browse.clicked.connect(self._choose_dir)
                grid.addWidget(browse, row, 2)
        layout.addLayout(grid)

        if self.info.kind is LinkKind.HTTP and not self.info.resumable:
            warn = QLabel("该链接不支持断点续传，暂停后可能需要重新下载")
            warn.setObjectName("HintError")
            layout.addWidget(warn)
        return body

    def _build_footer(self) -> QWidget:
        footer = QWidget()
        layout = QHBoxLayout(footer)
        layout.setContentsMargins(24, 6, 24, 20)
        layout.addStretch(1)
        cancel = QPushButton("取消")
        cancel.setObjectName("GhostButton")
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.clicked.connect(self.reject)
        confirm = QPushButton("开始下载")
        confirm.setObjectName("PrimaryButton")
        confirm.setCursor(Qt.CursorShape.PointingHandCursor)
        confirm.setDefault(True)
        confirm.clicked.connect(self._on_confirm)
        layout.addWidget(cancel)
        layout.addWidget(confirm)
        return footer

    # ------------------------------------------------------------------ 逻辑
    def _source_text(self) -> str:
        url = self.info.url or ""
        return url if len(url) <= 96 else url[:93] + "..."

    def _format_text(self) -> str:
        ext = extension_of(self.info.name)
        mime = self.info.mime or "未知"
        if ext:
            return f"{ext.upper()} · {mime} · {category_label(self.info.name, self.info.mime)}"
        return f"{mime} · {category_label(self.info.name, self.info.mime)}"

    def _method_text(self) -> str:
        label = KIND_LABELS.get(self.info.kind, "下载")
        if self.info.kind is LinkKind.HTTP:
            return f"{label}（{self._threads} 线程并行）"
        return f"{label}（libtorrent）"

    def _choose_dir(self):
        directory = QFileDialog.getExistingDirectory(self, "选择保存目录", self.save_dir)
        if directory:
            self.save_dir = directory
            if self.dir_label is not None:
                self.dir_label.setText(directory)

    def _on_confirm(self):
        name = self.name_edit.text().strip()
        if not name:
            self.name_edit.setFocus()
            return
        self.info.name = name
        self._confirmed = True
        self.accept()

    @property
    def _threads(self) -> int:
        parent = self.parent()
        return getattr(parent, "thread_count", 8) if parent is not None else 8

    def result_info(self):
        """返回 (FileInfo, save_dir)；取消返回 None。"""
        if not self._confirmed:
            return None
        return self.info, self.save_dir

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._on_confirm()
            return
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)
