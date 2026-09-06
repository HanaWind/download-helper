"""下载任务卡片：展示进度、速度、状态，并提供暂停/继续/重试/删除操作。"""

from __future__ import annotations

import os

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFontMetrics
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
)

from ..core.base_task import BaseTask
from ..core.models import KIND_LABELS, LinkKind, TaskState, state_label
from ..core.utils import format_eta, format_size, format_speed
from .icons import get_icon
from .info_dialog import build_badge
from .theme import COLORS


class TaskCard(QFrame):
    pauseRequested = Signal(object)
    resumeRequested = Signal(object)
    retryRequested = Signal(object)
    removeRequested = Signal(object)
    openRequested = Signal(object)

    def __init__(self, task: BaseTask, parent=None):
        super().__init__(parent)
        self.task = task
        self._progress_state = "running"
        self.setObjectName("Card")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(96)

        root = QHBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(14)

        self.badge = build_badge(task.info.name, task.info.mime, 46)
        root.addWidget(self.badge, 0, Qt.AlignmentFlag.AlignTop)

        middle = QVBoxLayout()
        middle.setSpacing(7)
        root.addLayout(middle, 1)

        top = QHBoxLayout()
        top.setSpacing(8)
        self.name_label = QLabel(task.info.name)
        self.name_label.setStyleSheet("font-size: 14px; font-weight: 600;")
        self.name_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        top.addWidget(self.name_label, 1)
        top.addLayout(self._build_buttons())
        middle.addLayout(top)

        bar_row = QHBoxLayout()
        bar_row.setSpacing(10)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setRange(0, 100)
        self.bar.setFixedHeight(8)
        bar_row.addWidget(self.bar, 1)
        self.percent_label = QLabel("0%")
        self.percent_label.setObjectName("Muted")
        self.percent_label.setFixedWidth(46)
        self.percent_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        bar_row.addWidget(self.percent_label)
        middle.addLayout(bar_row)

        self.meta_label = QLabel()
        self.meta_label.setObjectName("Muted")
        middle.addWidget(self.meta_label)

        self.sync()

    # ------------------------------------------------------------------ 按钮
    def _build_buttons(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setSpacing(6)
        self.pause_button = QToolButton()
        self.pause_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.pause_button.setToolTip("暂停")
        self.pause_button.clicked.connect(self._on_pause_clicked)
        self.retry_button = QToolButton()
        self.retry_button.setIcon(get_icon("refresh", COLORS["muted"], 18))
        self.retry_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.retry_button.setToolTip("重试")
        self.retry_button.clicked.connect(lambda: self.retryRequested.emit(self.task))
        self.folder_button = QToolButton()
        self.folder_button.setIcon(get_icon("folder", COLORS["muted"], 18))
        self.folder_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.folder_button.setToolTip("打开文件所在目录")
        self.folder_button.clicked.connect(lambda: self.openRequested.emit(self.task))
        self.remove_button = QToolButton()
        self.remove_button.setIcon(get_icon("trash", COLORS["muted"], 18))
        self.remove_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.remove_button.setToolTip("删除任务")
        self.remove_button.clicked.connect(lambda: self.removeRequested.emit(self.task))
        for button in (self.pause_button, self.retry_button, self.folder_button, self.remove_button):
            layout.addWidget(button)
        return layout

    def _on_pause_clicked(self):
        if self.task.state is TaskState.PAUSED or self.task.state is TaskState.QUEUED:
            self.resumeRequested.emit(self.task)
        else:
            self.pauseRequested.emit(self.task)

    # ------------------------------------------------------------------ 刷新
    def sync(self):
        task = self.task
        metrics = QFontMetrics(self.name_label.font())
        self.name_label.setText(
            metrics.elidedText(task.info.name, Qt.TextElideMode.ElideMiddle, 460)
        )
        self.name_label.setToolTip(task.info.name)

        percent = task.percent
        self.bar.setValue(int(percent))
        self.percent_label.setText(f"{percent:.0f}%")

        state_key = {
            TaskState.PAUSED: "paused",
            TaskState.ERROR: "error",
            TaskState.FINISHED: "finished",
            TaskState.CANCELED: "paused",
        }.get(task.state, "running")
        if state_key != self._progress_state:
            self._progress_state = state_key
            self.bar.setProperty("state", state_key)
            self.bar.style().unpolish(self.bar)
            self.bar.style().polish(self.bar)

        self._sync_buttons()

        kind = KIND_LABELS.get(task.kind, "")
        parts = [
            f"{format_size(task.received)} / {format_size(task.total)}",
            format_speed(task.speed),
        ]
        if task.state is TaskState.DOWNLOADING and task.eta >= 0:
            parts.append(f"剩余 {format_eta(task.eta)}")
        if task.kind is LinkKind.HTTP and getattr(task, "threads", 0):
            parts.append(f"{task.threads} 线程")
        parts.append(state_label(task.state))
        if task.kind is not LinkKind.HTTP:
            parts.append(kind)
        if task.message and task.state not in (TaskState.FINISHED,):
            parts.append(task.message)
        self.meta_label.setText("  ·  ".join(parts))
        if task.state is TaskState.ERROR:
            self.meta_label.setStyleSheet(f"color: {COLORS['danger']};")
        elif task.state is TaskState.FINISHED:
            self.meta_label.setStyleSheet(f"color: {COLORS['success']};")
        else:
            self.meta_label.setStyleSheet(f"color: {COLORS['muted']};")

    def _sync_buttons(self):
        state = self.task.state
        if state is TaskState.PAUSED or state is TaskState.QUEUED:
            self.pause_button.setIcon(get_icon("play", COLORS["success"], 18))
            self.pause_button.setToolTip("继续")
        elif state is TaskState.FINISHED or state is TaskState.CANCELED:
            self.pause_button.setIcon(get_icon("check", COLORS["muted"], 18))
            self.pause_button.setToolTip("已完成")
            self.pause_button.setEnabled(False)
        else:
            self.pause_button.setIcon(get_icon("pause", COLORS["text"], 18))
            self.pause_button.setToolTip("暂停")
            self.pause_button.setEnabled(True)
        if state is not TaskState.FINISHED and state is not TaskState.CANCELED:
            self.pause_button.setEnabled(True)
        self.retry_button.setVisible(state is TaskState.ERROR)
        self.folder_button.setVisible(bool(self.task.save_path) or os.path.isdir(self.task.save_dir))


def reveal_file(task: BaseTask):
    """在文件管理器中定位已下载的文件/目录。"""
    path = task.save_path if task.save_path and os.path.exists(task.save_path) else task.save_dir
    if not path:
        return
    if os.name == "nt" and task.save_path and os.path.exists(task.save_path):
        import subprocess

        try:
            subprocess.Popen(["explorer", "/select,", os.path.normpath(task.save_path)])
            return
        except Exception:
            pass
    QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.normpath(path)))
