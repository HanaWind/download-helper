"""设置弹窗：下载目录、单文件线程数、同时下载任务数、失败重试次数。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..core.models import Config
from .base import FramelessDialog, TitleBar
from .icons import get_icon
from .theme import COLORS


class SettingsDialog(FramelessDialog):
    def __init__(self, config: Config, parent=None):
        super().__init__(parent)
        self.config = config
        self.setMinimumWidth(460)
        self.setModal(True)

        self.content_layout.addWidget(
            TitleBar(self, "下载设置", "调整线程数与并发任务数", icon_name="settings")
        )
        self.content_layout.addWidget(self._build_body())
        self.content_layout.addWidget(self._build_footer())

    def _build_body(self) -> QWidget:
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(24, 18, 24, 12)
        layout.setSpacing(16)

        grid = QGridLayout()
        grid.setVerticalSpacing(12)
        grid.setHorizontalSpacing(12)

        self.dir_edit = QLineEdit(self.config.save_dir)
        browse = QToolButton()
        browse.setObjectName("IconButton")
        browse.setIcon(get_icon("folder", COLORS["text"], 16))
        browse.setCursor(Qt.CursorShape.PointingHandCursor)
        browse.clicked.connect(self._choose_dir)
        dir_row = QHBoxLayout()
        dir_row.setSpacing(8)
        dir_row.addWidget(self.dir_edit, 1)
        dir_row.addWidget(browse)

        self.threads_spin = QSpinBox()
        self.threads_spin.setRange(1, 16)
        self.threads_spin.setValue(self.config.threads)
        self.active_spin = QSpinBox()
        self.active_spin.setRange(1, 3)
        self.active_spin.setValue(self.config.max_active)
        self.retry_spin = QSpinBox()
        self.retry_spin.setRange(0, 10)
        self.retry_spin.setValue(self.config.max_retry)

        rows = [
            ("保存目录", dir_row),
            ("单文件线程数", self.threads_spin),
            ("同时下载任务数", self.active_spin),
            ("失败重试次数", self.retry_spin),
        ]
        for row, (label, widget) in enumerate(rows):
            label_widget = QLabel(label)
            label_widget.setObjectName("Muted")
            label_widget.setFixedWidth(110)
            grid.addWidget(label_widget, row, 0)
            if isinstance(widget, QHBoxLayout):
                grid.addLayout(widget, row, 1)
            else:
                grid.addWidget(widget, row, 1)

        layout.addLayout(grid)
        tip = QLabel("同时下载任务数上限为 3（单个文件内部由多线程并行下载）")
        tip.setObjectName("Hint")
        tip.setWordWrap(True)
        layout.addWidget(tip)
        layout.addStretch(1)
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
        save = QPushButton("保存")
        save.setObjectName("PrimaryButton")
        save.setCursor(Qt.CursorShape.PointingHandCursor)
        save.clicked.connect(self._on_save)
        layout.addWidget(cancel)
        layout.addWidget(save)
        return footer

    def _choose_dir(self):
        directory = QFileDialog.getExistingDirectory(self, "选择默认保存目录", self.dir_edit.text())
        if directory:
            self.dir_edit.setText(directory)

    def _on_save(self):
        self.config.save_dir = self.dir_edit.text().strip() or self.config.save_dir
        self.config.threads = self.threads_spin.value()
        self.config.max_active = self.active_spin.value()
        self.config.max_retry = self.retry_spin.value()
        self.config.clamp()
        self.config.save()
        self.accept()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._on_save()
            return
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)
