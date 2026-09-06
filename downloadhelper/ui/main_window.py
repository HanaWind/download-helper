"""主窗口：链接输入、文件信息确认、任务列表与全局控制。"""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..core.manager import DownloadManager
from ..core.models import Config, FileInfo, TaskState
from ..core.probe import MagnetProbe, UrlProbe
from ..core.utils import detect_kind, format_speed
from .base import FramelessWindow, TitleBar, add_size_grip
from .confirm_dialog import ConfirmDialog
from .icons import app_icon, get_icon
from .info_dialog import FileInfoDialog
from .settings_dialog import SettingsDialog
from .task_card import TaskCard, reveal_file
from .theme import COLORS, QSS, get_theme


class MainWindow(FramelessWindow):
    def __init__(self):
        super().__init__()
        self.config = Config.load()
        self.thread_count = self.config.threads
        self.manager = DownloadManager(self.config, self)
        self._cards: dict = {}
        self._probe = None

        self.setWindowTitle("Hana Download Helper")
        self.setWindowIcon(app_icon(64))
        self.resize(1040, 700)
        self.setMinimumSize(920, 580)

        self._build_ui()
        self.manager.taskAdded.connect(self._add_card)
        self.manager.taskRemoved.connect(self._remove_card)
        self.manager.load_state()

        self._timer = QTimer(self)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    # ------------------------------------------------------------------ 构建界面
    def _build_ui(self):
        self.title_bar = TitleBar(self, "Hana Download Helper")
        self.content_layout.addWidget(self.title_bar)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(24, 16, 24, 8)
        body_layout.setSpacing(14)
        self.content_layout.addWidget(body, 1)

        body_layout.addLayout(self._build_header())
        body_layout.addLayout(self._build_url_row())

        self.hint_label = QLabel("")
        self.hint_label.setObjectName("Hint")
        self.hint_label.setVisible(False)
        body_layout.addWidget(self.hint_label)

        body_layout.addWidget(self._build_list(), 1)
        body_layout.addLayout(self._build_footer())

    def _build_header(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setSpacing(12)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        title = QLabel("新建下载任务")
        title.setObjectName("HeroTitle")
        subtitle = QLabel("支持 HTTP/HTTPS 多线程分块、磁力链接与种子文件")
        subtitle.setObjectName("HeroSubtitle")
        text_layout.addWidget(title)
        text_layout.addWidget(subtitle)
        layout.addLayout(text_layout)
        layout.addStretch(1)

        self.resume_all_button = QPushButton("全部开始")
        self.resume_all_button.setObjectName("GhostButton")
        self.resume_all_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.resume_all_button.clicked.connect(self._resume_all)

        self.pause_all_button = QPushButton("全部暂停")
        self.pause_all_button.setObjectName("GhostButton")
        self.pause_all_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.pause_all_button.clicked.connect(self._pause_all)

        self.clear_button = QPushButton("清除已完成")
        self.clear_button.setObjectName("GhostButton")
        self.clear_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_button.clicked.connect(self._clear_finished)

        self.settings_button = QToolButton()
        self.settings_button.setObjectName("IconButton")
        self.settings_button.setIcon(get_icon("settings", COLORS["text"], 18))
        self.settings_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.settings_button.setToolTip("下载设置")
        self.settings_button.clicked.connect(self._open_settings)

        for widget in (self.resume_all_button, self.pause_all_button, self.clear_button,
                       self.settings_button):
            layout.addWidget(widget)
        return layout

    def _build_url_row(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setSpacing(10)

        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText(
            "粘贴下载链接（HTTP / HTTPS / 磁力链接 / 种子文件），回车开始解析"
        )
        self.url_edit.setMinimumHeight(44)
        self.url_edit.returnPressed.connect(self._on_submit)
        self.url_edit.setClearButtonEnabled(True)
        layout.addWidget(self.url_edit, 1)

        self.confirm_button = QPushButton("确定")
        self.confirm_button.setObjectName("PrimaryButton")
        self.confirm_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.confirm_button.setMinimumHeight(44)
        self.confirm_button.clicked.connect(self._on_submit)
        layout.addWidget(self.confirm_button)

        self.cancel_probe_button = QToolButton()
        self.cancel_probe_button.setObjectName("IconButton")
        self.cancel_probe_button.setIcon(get_icon("close", COLORS["text"], 18))
        self.cancel_probe_button.setToolTip("取消解析")
        self.cancel_probe_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_probe_button.setVisible(False)
        self.cancel_probe_button.clicked.connect(self._cancel_probe)
        layout.addWidget(self.cancel_probe_button)
        return layout

    def _build_list(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.list_container = QWidget()
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(2, 2, 10, 2)
        self.list_layout.setSpacing(10)
        self.list_layout.addStretch(1)
        self.scroll.setWidget(self.list_container)
        layout.addWidget(self.scroll, 1)

        self.empty_state = self._build_empty_state()
        layout.addWidget(self.empty_state)
        return container

    def _build_empty_state(self) -> QWidget:
        widget = QWidget()
        widget.setObjectName("EmptyState")
        layout = QVBoxLayout(widget)
        layout.setSpacing(10)
        layout.setContentsMargins(0, 40, 0, 40)
        icon_label = QLabel()
        icon_label.setPixmap(get_icon("download", "#2C3854", 72).pixmap(72, 72))
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title = QLabel("还没有下载任务")
        title.setStyleSheet("font-size: 15px; font-weight: 600; color: #6F7C96;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle = QLabel("在上方粘贴链接并按下回车，即可解析文件信息并开始下载")
        subtitle.setStyleSheet("color: #5B6780;")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_label)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        return widget

    def _build_footer(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setContentsMargins(2, 6, 0, 0)
        self.stats_label = QLabel("就绪")
        self.stats_label.setObjectName("Muted")
        layout.addWidget(self.stats_label)
        layout.addStretch(1)
        add_size_grip(layout)
        return layout

    # ------------------------------------------------------------------ 解析链接
    def _on_submit(self):
        url = self.url_edit.text().strip()
        if not url:
            self._show_hint("请先输入下载链接", error=True)
            return
        if self._probe is not None:
            return
        kind = detect_kind(url)
        if kind.value == "magnet":
            worker = MagnetProbe(url, timeout=90, parent=self)
            hint = "正在通过 DHT 网络获取磁力链接的种子信息…"
        else:
            worker = UrlProbe(url, parent=self)
            hint = "正在获取文件信息…"
        worker.result.connect(self._on_probe_result)
        worker.error.connect(self._on_probe_error)
        worker.finished.connect(self._on_probe_finished)
        self._probe = worker
        self._set_busy(True, hint)
        worker.start()

    def _cancel_probe(self):
        worker = self._probe
        if worker is None:
            return
        if hasattr(worker, "cancel"):
            worker.cancel()
        worker.quit()
        worker.wait(2000)

    def _on_probe_finished(self):
        self._probe = None
        self._set_busy(False)
        self._update_empty_state()

    def _on_probe_result(self, info: FileInfo):
        dialog = FileInfoDialog(info, self.config.save_dir, threads=self.config.threads, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        result = dialog.result_info()
        if not result:
            return
        info, save_dir = result
        self.config.save_dir = save_dir
        self.config.save()
        self.url_edit.clear()
        task = self.manager.add_task(info, save_dir)
        self._show_hint(f"已添加任务：{task.info.name}", ok=True)

    def _on_probe_error(self, message: str):
        self._show_hint(message, error=True)

    def _set_busy(self, busy: bool, message: str = ""):
        self.confirm_button.setEnabled(not busy)
        self.cancel_probe_button.setVisible(busy)
        self.hint_label.setVisible(bool(message))
        if message:
            self.hint_label.setObjectName("Hint")
            self.hint_label.setStyleSheet(f"color: {COLORS['muted']}; font-size: 12px;")
            self.hint_label.setText(message)

    def _show_hint(self, message: str, error: bool = False, ok: bool = False):
        name = "HintError" if error else ("HintOk" if ok else "Hint")
        color = COLORS["danger"] if error else (COLORS["success"] if ok else COLORS["muted"])
        self.hint_label.setObjectName(name)
        self.hint_label.setStyleSheet(f"color: {color}; font-size: 12px;")
        self.hint_label.setText(message)
        self.hint_label.setVisible(True)
        QTimer.singleShot(6000, self._clear_hint)

    def _clear_hint(self):
        if self._probe is None:
            self.hint_label.setVisible(False)

    # ------------------------------------------------------------------ 任务卡片
    def _add_card(self, task):
        if task.id in self._cards:
            return
        card = TaskCard(task)
        card.pauseRequested.connect(self._pause_task)
        card.resumeRequested.connect(self._resume_task)
        card.retryRequested.connect(self._retry_task)
        card.removeRequested.connect(self._remove_task)
        card.openRequested.connect(lambda t: reveal_file(t))
        self._cards[task.id] = card
        self.list_layout.insertWidget(0, card)
        self._update_empty_state()

    def _remove_card(self, task):
        card = self._cards.pop(task.id, None)
        if card is not None:
            self.list_layout.removeWidget(card)
            card.deleteLater()
        self._update_empty_state()

    def _update_empty_state(self):
        empty = len(self.manager.tasks) == 0
        self.empty_state.setVisible(empty)
        self.scroll.setVisible(not empty)

    def _pause_task(self, task):
        task.pause()

    def _resume_task(self, task):
        task.resume()
        self.manager.pump()

    def _retry_task(self, task):
        task.error = ""
        task.state = TaskState.QUEUED
        task.emit_updated(force=True)
        self.manager.pump()

    def _remove_task(self, task):
        finished = task.state is TaskState.FINISHED
        if not finished:
            ok = ConfirmDialog.ask(
                self,
                "删除任务",
                "删除任务会清除已下载的分片文件，确定继续吗？",
                confirm_text="删除",
                danger=True,
            )
            if not ok:
                return
        self.manager.remove_task(task.id, delete_files=not finished)

    # ------------------------------------------------------------------ 全局控制
    def _pause_all(self):
        self.manager.pause_all()

    def _resume_all(self):
        self.manager.resume_all()

    def _clear_finished(self):
        self.manager.clear_finished()

    def _open_settings(self):
        dialog = SettingsDialog(self.config, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.thread_count = self.config.threads
            self.manager.config = self.config
            self.manager.pump()
            self._show_hint("设置已保存", ok=True)

    # ------------------------------------------------------------------ 定时刷新
    def _tick(self):
        self.manager.tick()
        for task in self.manager.tasks:
            card = self._cards.get(task.id)
            if card is not None:
                card.sync()
        active, queued, finished = self.manager.counts()
        speed = format_speed(self.manager.total_speed)
        self.stats_label.setText(
            f"总速度 {speed}    下载中 {active}/{self.config.max_active}"
            f"    排队 {queued}    已完成 {finished}"
        )

    # ------------------------------------------------------------------ 窗口状态
    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange and hasattr(self, "title_bar"):
            self.title_bar.btn_max.set_icon_name(
                "restore" if self.isMaximized() else "maximize"
            )

    # ------------------------------------------------------------------ 退出
    def closeEvent(self, event):
        try:
            self.manager.pause_all()
            self.manager.save_state()
            self.config.save()
        except Exception:
            pass
        super().closeEvent(event)


def run() -> int:
    import sys

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Hana Download Helper")
    app.setApplicationDisplayName("Hana Download Helper")
    app.setWindowIcon(app_icon(64))
    app.setAttribute(Qt.ApplicationAttribute.AA_DontCreateNativeWidgetSiblings, True)
    app.setStyleSheet(QSS)

    # 按已保存的配置应用主题（模式 / 背景图 / 不透明度 / 模糊度）
    cfg = Config.load()
    get_theme().configure(
        mode=cfg.theme_mode,
        image=cfg.bg_image,
        opacity=cfg.bg_opacity,
        blur=cfg.bg_blur,
    )
    get_theme().apply(app)

    window = MainWindow()
    window.show()
    return app.exec()
