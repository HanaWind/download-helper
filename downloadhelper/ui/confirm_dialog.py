"""主题化确认弹窗：替代系统 QMessageBox，保证深色/浅色下文字都清晰可读。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .base import FramelessDialog, TitleBar
from .icons import get_icon
from .theme import COLORS


class ConfirmDialog(FramelessDialog):
    """带图标、说明文字与取消/确认按钮的确认弹窗。"""

    def __init__(self, title: str, message: str, confirm_text: str = "确定",
                 cancel_text: str = "取消", danger: bool = True, parent=None):
        super().__init__(parent)
        self._confirmed = False
        self.setMinimumWidth(430)
        self.setModal(True)

        self.content_layout.addWidget(
            TitleBar(self, title, icon_name="alert", show_buttons=False)
        )
        self.content_layout.addWidget(self._build_body(message, danger))
        self.content_layout.addWidget(self._build_footer(confirm_text, cancel_text, danger))

    def _build_body(self, message: str, danger: bool) -> QWidget:
        body = QWidget()
        # 不透明面板背景，保证文字（浅色主题为黑色）在任何主题/背景图下都清晰可读
        body.setStyleSheet(f"background: {COLORS['panel']}; border-radius: 10px;")
        layout = QHBoxLayout(body)
        layout.setContentsMargins(24, 20, 24, 14)
        layout.setSpacing(14)

        icon_label = QLabel()
        color = COLORS["danger"] if danger else COLORS["accent"]
        icon_label.setPixmap(get_icon("alert", color, 30).pixmap(30, 30))
        icon_label.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.addWidget(icon_label)

        text = QLabel(message)
        # 文字颜色跟随当前主题，保证与背景有足够对比度（浅色主题下为深色/黑色文字）
        text.setStyleSheet(f"color: {COLORS['text']}; font-size: 13.5px; background: transparent;")
        text.setWordWrap(True)
        text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        text.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(text, 1)
        return body

    def _build_footer(self, confirm_text: str, cancel_text: str, danger: bool) -> QWidget:
        footer = QWidget()
        layout = QHBoxLayout(footer)
        layout.setContentsMargins(24, 6, 24, 20)
        layout.addStretch(1)

        cancel = QPushButton(cancel_text)
        cancel.setObjectName("GhostButton")
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.clicked.connect(self.reject)

        confirm = QPushButton(confirm_text)
        confirm.setObjectName("DangerButton" if danger else "PrimaryButton")
        confirm.setCursor(Qt.CursorShape.PointingHandCursor)
        confirm.setDefault(True)
        confirm.clicked.connect(self._on_confirm)

        layout.addWidget(cancel)
        layout.addWidget(confirm)
        return footer

    def _on_confirm(self):
        self._confirmed = True
        self.accept()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._on_confirm()
            return
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)

    @staticmethod
    def ask(parent, title: str, message: str, confirm_text: str = "确定",
            cancel_text: str = "取消", danger: bool = True) -> bool:
        dialog = ConfirmDialog(title, message, confirm_text, cancel_text, danger, parent)
        return dialog.exec() == QDialog.DialogCode.Accepted and dialog._confirmed
