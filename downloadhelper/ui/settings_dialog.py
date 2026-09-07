"""设置弹窗：下载设置与外观设置。"""

from __future__ import annotations

import os

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QSpinBox,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..core.models import THEME_MODES, Config
from .base import FramelessDialog, TitleBar
from .icons import get_icon
from .theme import COLORS, MODE_LABELS, get_theme

IMAGE_FILTER = "图片文件 (*.png *.jpg *.jpeg *.bmp *.webp *.gif);;所有文件 (*.*)"


class SettingsDialog(FramelessDialog):
    def __init__(self, config: Config, parent=None):
        super().__init__(parent)
        self.config = config
        self._backup = config.to_dict().copy()
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(40)
        self._preview_timer.timeout.connect(self._apply_preview)
        self.setMinimumWidth(620)
        self.setMinimumHeight(440)
        self.setModal(True)

        self.content_layout.addWidget(TitleBar(self, "设置", icon_name="settings"))
        self.content_layout.addWidget(self._build_body(), 1)
        self.content_layout.addWidget(self._build_footer())

    def _build_body(self) -> QWidget:
        body = QWidget()
        root = QHBoxLayout(body)
        root.setContentsMargins(20, 16, 20, 10)
        root.setSpacing(16)

        nav = QWidget()
        nav.setFixedWidth(118)
        nav_layout = QVBoxLayout(nav)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(6)
        self.download_nav = QPushButton("下载设置")
        self.appearance_nav = QPushButton("外观设置")
        for button in (self.download_nav, self.appearance_nav):
            button.setCheckable(True)
            button.setObjectName("SettingsNav")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            nav_layout.addWidget(button)
        nav_layout.addStretch(1)

        self.pages = QStackedWidget()
        self.pages.addWidget(self._build_download_page())
        self.pages.addWidget(self._build_appearance_page())
        self.download_nav.clicked.connect(lambda: self._select_page(0))
        self.appearance_nav.clicked.connect(lambda: self._select_page(1))
        self._select_page(0)

        root.addWidget(nav)
        root.addWidget(self.pages, 1)
        return body

    def _select_page(self, index: int):
        self.pages.setCurrentIndex(index)
        self.download_nav.setChecked(index == 0)
        self.appearance_nav.setChecked(index == 1)

    def _build_download_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(14)

        title = QLabel("下载设置")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setVerticalSpacing(14)
        grid.setHorizontalSpacing(12)
        self.dir_edit = QLineEdit(self.config.save_dir)
        browse = QToolButton()
        browse.setObjectName("IconButton")
        browse.setIcon(get_icon("folder", COLORS["text"], 16))
        browse.setToolTip("选择默认保存目录")
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
        tip = QLabel("同时下载任务数上限为 3；单个 HTTP 文件可使用多线程并行下载。")
        tip.setObjectName("Hint")
        tip.setWordWrap(True)
        layout.addWidget(tip)
        layout.addStretch(1)
        return page

    def _build_appearance_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(12)

        title = QLabel("外观设置")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)
        grid = QGridLayout()
        grid.setVerticalSpacing(12)
        grid.setHorizontalSpacing(12)

        self.theme_combo = QComboBox()
        for mode in THEME_MODES:
            self.theme_combo.addItem(MODE_LABELS[mode], mode)
        index = self.theme_combo.findData(self.config.theme_mode)
        self.theme_combo.setCurrentIndex(max(0, index))
        self.theme_combo.currentIndexChanged.connect(self._schedule_preview)
        self.theme_hint = QLabel("")
        self.theme_hint.setObjectName("Hint")

        self.bg_edit = QLineEdit(self.config.bg_image)
        self.bg_edit.setPlaceholderText("未使用背景图（可留空）")
        self.bg_edit.setReadOnly(True)
        choose = QToolButton()
        choose.setObjectName("IconButton")
        choose.setIcon(get_icon("folder", COLORS["text"], 16))
        choose.setToolTip("选择背景图片")
        choose.clicked.connect(self._choose_image)
        clear = QToolButton()
        clear.setObjectName("IconButton")
        clear.setIcon(get_icon("close", COLORS["text"], 16))
        clear.setToolTip("清除背景图")
        clear.clicked.connect(self._clear_image)
        bg_row = QHBoxLayout()
        bg_row.setSpacing(8)
        bg_row.addWidget(self.bg_edit, 1)
        bg_row.addWidget(choose)
        bg_row.addWidget(clear)

        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(0, 100)
        self.opacity_slider.setValue(self.config.bg_opacity)
        self.opacity_slider.valueChanged.connect(self._on_opacity_changed)
        self.opacity_label = QLabel(f"{self.config.bg_opacity}%")
        self.opacity_label.setObjectName("Muted")
        self.opacity_label.setFixedWidth(42)
        opacity_row = QHBoxLayout()
        opacity_row.addWidget(self.opacity_slider, 1)
        opacity_row.addWidget(self.opacity_label)

        self.blur_slider = QSlider(Qt.Orientation.Horizontal)
        self.blur_slider.setRange(0, 40)
        self.blur_slider.setValue(self.config.bg_blur)
        self.blur_slider.valueChanged.connect(self._on_blur_changed)
        self.blur_label = QLabel(f"{self.config.bg_blur}px")
        self.blur_label.setObjectName("Muted")
        self.blur_label.setFixedWidth(42)
        blur_row = QHBoxLayout()
        blur_row.addWidget(self.blur_slider, 1)
        blur_row.addWidget(self.blur_label)

        rows = [
            ("主题模式", self.theme_combo),
            ("当前效果", self.theme_hint),
            ("背景图片", bg_row),
            ("背景不透明度", opacity_row),
            ("背景模糊度", blur_row),
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
        hint = QLabel("拖动滑块即可实时预览，模糊半径越大背景越柔和。")
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addStretch(1)
        self._update_hint()
        return page

    def _build_footer(self) -> QWidget:
        footer = QWidget()
        layout = QHBoxLayout(footer)
        layout.setContentsMargins(20, 6, 20, 18)
        layout.addStretch(1)
        cancel = QPushButton("取消")
        cancel.setObjectName("GhostButton")
        cancel.clicked.connect(self._on_cancel)
        save = QPushButton("保存")
        save.setObjectName("PrimaryButton")
        save.clicked.connect(self._on_save)
        layout.addWidget(cancel)
        layout.addWidget(save)
        return footer

    def _choose_dir(self):
        directory = QFileDialog.getExistingDirectory(self, "选择默认保存目录", self.dir_edit.text())
        if directory:
            self.dir_edit.setText(directory)

    def _choose_image(self):
        start = self.bg_edit.text() or os.path.expanduser("~")
        path, _ = QFileDialog.getOpenFileName(self, "选择背景图片", start, IMAGE_FILTER)
        if path:
            self.bg_edit.setText(path)
            self._schedule_preview()

    def _clear_image(self):
        self.bg_edit.clear()
        self._schedule_preview()

    def _on_opacity_changed(self, value: int):
        self.opacity_label.setText(f"{value}%")
        self._schedule_preview()

    def _on_blur_changed(self, value: int):
        self.blur_label.setText(f"{value}px")
        self._schedule_preview()

    def _schedule_preview(self):
        self._preview_timer.start()

    def _apply_preview(self):
        theme = get_theme()
        theme.configure(
            mode=self.theme_combo.currentData(),
            image=self.bg_edit.text().strip(),
            opacity=self.opacity_slider.value(),
            blur=self.blur_slider.value(),
        )
        theme.apply()
        self._update_hint()

    def _update_hint(self):
        theme = get_theme()
        text = (f"当前：{theme.resolved_label}（7:00-19:00 浅色，其余深色）"
                if theme.mode == "auto" else f"当前：{theme.resolved_label}")
        if theme.has_background:
            text += " · 已启用背景图"
        self.theme_hint.setText(text)

    def _restore_backup(self):
        for key, value in self._backup.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)
        self.config.clamp()
        get_theme().configure(
            mode=self.config.theme_mode,
            image=self.config.bg_image,
            opacity=self.config.bg_opacity,
            blur=self.config.bg_blur,
        )
        get_theme().apply()

    def _on_save(self):
        self.config.save_dir = self.dir_edit.text().strip() or self.config.save_dir
        self.config.threads = self.threads_spin.value()
        self.config.max_active = self.active_spin.value()
        self.config.max_retry = self.retry_spin.value()
        self.config.theme_mode = self.theme_combo.currentData() or "dark"
        self.config.bg_image = self.bg_edit.text().strip()
        self.config.bg_opacity = self.opacity_slider.value()
        self.config.bg_blur = self.blur_slider.value()
        self.config.clamp()
        self.config.save()
        self._apply_preview()
        self.accept()

    def _on_cancel(self):
        self._preview_timer.stop()
        self._restore_backup()
        self.reject()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._on_save()
            return
        if event.key() == Qt.Key.Key_Escape:
            self._on_cancel()
            return
        super().keyPressEvent(event)
