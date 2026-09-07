"""任务基类：统一的状态、进度、速度与信号接口。"""

from __future__ import annotations

import threading
import time
import uuid
from collections import deque

from PySide6.QtCore import QObject, Signal

from .models import FileInfo, TaskState


class BaseTask(QObject):
    """所有下载任务的基类。

    任务对象存活于 GUI 线程，工作线程只更新计数并通过信号通知界面，
    Qt 的自动连接会将其转为队列调用，因此线程安全。
    """

    updated = Signal(object)   # 进度/状态变化
    finished = Signal(object)  # 下载完成
    failed = Signal(object, str)

    MIN_EMIT_INTERVAL = 0.12

    def __init__(self, info: FileInfo, save_dir: str, parent=None):
        super().__init__(parent)
        self.id = uuid.uuid4().hex
        self.info = info
        self.save_dir = save_dir
        self.state = TaskState.QUEUED
        self.total = int(info.size) if info and info.size and int(info.size) > 0 else -1
        self.received = 0
        self.speed = 0.0
        self.eta = -1
        self.message = ""
        self.error = ""
        self.save_path = ""
        self.created_at = time.time()

        self._lock = threading.RLock()
        self._samples: deque = deque(maxlen=16)
        self._last_emit = 0.0

    # ------------------------------------------------------------------ 基础属性
    @property
    def name(self) -> str:
        return self.info.name or "未命名文件"

    @property
    def kind(self):
        return self.info.kind

    @property
    def is_active(self) -> bool:
        return self.state in (TaskState.DOWNLOADING, TaskState.PREPARING)

    @property
    def percent(self) -> float:
        if self.state == TaskState.FINISHED:
            return 100.0
        if self.total > 0:
            return max(0.0, min(100.0, self.received * 100.0 / self.total))
        return 0.0

    # ------------------------------------------------------------------ 进度
    def add_bytes(self, count: int) -> None:
        with self._lock:
            self.received += int(count)
            if self.total > 0 and self.received > self.total:
                self.received = self.total
            self._samples.append((time.monotonic(), self.received))
        self.emit_updated()

    def set_received(self, value: int, speed: float = None) -> None:
        with self._lock:
            self.received = int(value)
            self._samples.append((time.monotonic(), self.received))
            if speed is not None:
                self.speed = float(speed)
        self.emit_updated()

    def refresh_speed(self) -> None:
        """由管理器定时调用，使用滑动窗口计算速度并估算剩余时间。"""
        with self._lock:
            if len(self._samples) < 2:
                current = 0.0
            else:
                t0, b0 = self._samples[0]
                t1, b1 = self._samples[-1]
                dt = t1 - t0
                if dt <= 0.2:
                    current = self.speed
                elif time.monotonic() - t1 > 1.6:
                    current = 0.0
                else:
                    current = max(0.0, (b1 - b0) / dt)
            if self.state in (TaskState.PAUSED, TaskState.FINISHED, TaskState.ERROR,
                              TaskState.QUEUED, TaskState.CANCELED):
                current = 0.0
            self.speed = current if self.speed <= 0 else self.speed * 0.35 + current * 0.65
            if self.speed < 1024:
                self.speed = 0.0 if current == 0 else self.speed
            if self.speed > 0 and self.total > 0 and self.received < self.total:
                self.eta = max(0, int((self.total - self.received) / self.speed))
            else:
                self.eta = -1

    def emit_updated(self, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last_emit < self.MIN_EMIT_INTERVAL:
            return
        self._last_emit = now
        self.updated.emit(self)

    def set_state(self, state: TaskState, message: str = None) -> None:
        self.state = state
        if message is not None:
            self.message = message
        if state in (TaskState.PAUSED, TaskState.FINISHED, TaskState.ERROR,
                     TaskState.QUEUED, TaskState.CANCELED):
            self.speed = 0.0
            self.eta = -1
        self.emit_updated(force=True)

    def fail(self, message: str) -> None:
        self.error = message
        self.state = TaskState.ERROR
        self.speed = 0.0
        self.eta = -1
        self.message = message
        self.emit_updated(force=True)
        self.failed.emit(self, message)

    # ------------------------------------------------------------------ 控制接口
    def start(self):  # pragma: no cover - 由子类实现
        raise NotImplementedError

    def pause(self):  # pragma: no cover
        raise NotImplementedError

    def resume(self):  # pragma: no cover
        self.start()

    def cancel(self):  # pragma: no cover
        raise NotImplementedError

    def retry(self):
        self.error = ""
        self.state = TaskState.QUEUED
        self.emit_updated(force=True)
        self.resume()

    # ------------------------------------------------------------------ 持久化
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "info": self.info.to_dict(),
            "save_dir": self.save_dir,
            "received": self.received,
            "save_path": self.save_path,
        }

    def describe(self) -> str:
        return f"{self.name} ({self.total})"
