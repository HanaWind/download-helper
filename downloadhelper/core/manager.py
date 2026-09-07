"""下载管理器：调度任务（最多同时 3 个文件）、刷新速度与状态、持久化任务列表。"""

from __future__ import annotations

import os
from typing import Dict, List, Optional

from PySide6.QtCore import QObject, QTimer, Signal

from .base_task import BaseTask
from .http_task import HttpDownloadTask
from .logging_setup import get_logger
from .models import Config, FileInfo, LinkKind, TaskState, tasks_path
from .torrent_task import TorrentDownloadTask
from .utils import sanitize_filename

logger = get_logger()

MAX_CONCURRENT = 3


def create_task(info: FileInfo, save_dir: str, config: Config) -> BaseTask:
    if info.kind in (LinkKind.MAGNET, LinkKind.TORRENT):
        return TorrentDownloadTask(info, save_dir)
    return HttpDownloadTask(info, save_dir, threads=config.threads, max_retry=config.max_retry)


class DownloadManager(QObject):
    taskAdded = Signal(object)
    taskRemoved = Signal(object)
    taskFinished = Signal(object)
    statsChanged = Signal()

    def __init__(self, config: Config, parent=None):
        super().__init__(parent)
        self.config = config
        self.tasks: List[BaseTask] = []
        self._index: Dict[str, BaseTask] = {}
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(1200)
        self._save_timer.timeout.connect(self.save_state)

    # ------------------------------------------------------------------ 增删
    def add_task(self, info: FileInfo, save_dir: str = None) -> BaseTask:
        save_dir = save_dir or self.config.save_dir
        try:
            os.makedirs(save_dir, exist_ok=True)
        except OSError as exc:
            raise OSError(f"无法创建保存目录：{save_dir} ({exc})") from exc
        info.name = sanitize_filename(info.name or "", default="download")
        task = create_task(info, save_dir, self.config)
        task.updated.connect(lambda t=task: self._on_task_updated(t))
        task.finished.connect(lambda t=task: self._on_task_finished(t))
        task.failed.connect(lambda t, _message: self._on_task_failed(t))
        self.tasks.append(task)
        self._index[task.id] = task
        logger.info("添加任务：%s（类型=%s，保存至 %s）", info.name, info.kind.value, save_dir)
        self.taskAdded.emit(task)
        self._schedule_save()
        self.pump()
        return task

    def remove_task(self, task_id: str, delete_files: bool = False) -> Optional[BaseTask]:
        task = self._index.pop(task_id, None)
        if task is None:
            return None
        logger.info("移除任务：%s（删除文件=%s）", task.info.name, delete_files)
        try:
            task.cancel(remove_files=delete_files)
        except Exception:
            pass
        if task in self.tasks:
            self.tasks.remove(task)
        self.taskRemoved.emit(task)
        self._schedule_save()
        self.pump()
        return task

    def get(self, task_id: str) -> Optional[BaseTask]:
        return self._index.get(task_id)

    def clear_finished(self):
        for task in [t for t in self.tasks if t.state is TaskState.FINISHED]:
            self.remove_task(task.id, delete_files=False)

    # ------------------------------------------------------------------ 调度
    def pump(self):
        """保证同时下载的文件数不超过上限。"""
        active = [t for t in self.tasks if t.is_active]
        if len(active) >= self.config.max_active:
            return
        for task in self.tasks:
            if len(active) >= self.config.max_active:
                break
            if task.state in (TaskState.QUEUED,):
                try:
                    task.start()
                except Exception as exc:
                    task.fail(str(exc))
                active.append(task)

    def pause_all(self):
        for task in self.tasks:
            if task.is_active or task.state is TaskState.QUEUED:
                task.pause()

    def resume_all(self):
        for task in self.tasks:
            if task.state in (TaskState.PAUSED, TaskState.ERROR):
                task.state = TaskState.QUEUED
                task.error = ""
                task.emit_updated(force=True)
        self.pump()

    # ------------------------------------------------------------------ 定时刷新
    def tick(self):
        for task in self.tasks:
            if task.state in (TaskState.DOWNLOADING, TaskState.PREPARING):
                task.refresh_speed()
        self.statsChanged.emit()
        self.pump()

    @property
    def total_speed(self) -> float:
        return sum(t.speed for t in self.tasks if t.is_active)

    def counts(self):
        active = queued = finished = 0
        for task in self.tasks:
            if task.is_active:
                active += 1
            elif task.state is TaskState.QUEUED:
                queued += 1
            elif task.state is TaskState.FINISHED:
                finished += 1
        return active, queued, finished

    # ------------------------------------------------------------------ 事件
    def _on_task_updated(self, task: BaseTask):
        self._schedule_save()

    def _on_task_finished(self, task: BaseTask):
        logger.info("任务结束：%s 状态=%s", task.info.name, task.state.name)
        self.taskFinished.emit(task)
        self._schedule_save()
        self.pump()

    def _on_task_failed(self, task: BaseTask):
        logger.error("任务失败：%s 原因=%s", task.info.name, task.error)
        self._schedule_save()
        self.pump()

    def _schedule_save(self):
        self._save_timer.start()

    # ------------------------------------------------------------------ 持久化
    def save_state(self):
        data = []
        for task in self.tasks:
            if task.state is TaskState.CANCELED:
                continue
            payload = task.to_dict()
            payload["state"] = task.state.value
            data.append(payload)
        try:
            import json

            tmp = tasks_path() + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fp:
                json.dump(data, fp, ensure_ascii=False, indent=2)
            os.replace(tmp, tasks_path())
        except OSError:
            pass

    def load_state(self):
        import json

        try:
            with open(tasks_path(), "r", encoding="utf-8") as fp:
                data = json.load(fp)
        except (OSError, ValueError):
            return
        for payload in data:
            try:
                task = self._task_from_dict(payload)
            except Exception:
                continue
            if task is None:
                continue
            task.updated.connect(lambda t=task: self._on_task_updated(t))
            task.finished.connect(lambda t=task: self._on_task_finished(t))
            task.failed.connect(lambda t, _message: self._on_task_failed(t))
            task.state = TaskState.QUEUED
            if not task.save_dir:
                continue
            self.tasks.append(task)
            self._index[task.id] = task
            self.taskAdded.emit(task)
        self.pump()

    def _task_from_dict(self, payload: dict):
        task_type = payload.get("type", "http")
        if task_type == "torrent":
            task = TorrentDownloadTask.from_dict(payload)
        else:
            task = HttpDownloadTask.from_dict(
                payload, threads=self.config.threads, max_retry=self.config.max_retry
            )
        if payload.get("state") == TaskState.FINISHED.value:
            task.state = TaskState.FINISHED
            task.received = task.total if task.total > 0 else task.received
        return task
