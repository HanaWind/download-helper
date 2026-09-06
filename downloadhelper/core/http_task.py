"""HTTP(S) 多线程分块下载任务：分片并行、断点续传、暂停/继续、超时重试。"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass
from typing import Dict, List

import requests

from .base_task import BaseTask
from .models import TaskState
from .probe import DEFAULT_HEADERS
from .utils import sanitize_filename, unique_path

BLOCK_SIZE = 64 * 1024
MIN_CHUNK_SIZE = 512 * 1024
CONNECT_TIMEOUT = 10
READ_TIMEOUT = 30


class _PauseRequested(Exception):
    """内部信号：用户暂停，需要重新等待。"""


@dataclass
class Chunk:
    index: int
    start: int
    end: int  # 含，-1 表示未知长度（单连接流式下载）
    offset: int = 0
    done: bool = False

    @property
    def length(self) -> int:
        if self.end < 0:
            return -1
        return self.end - self.start + 1

    def remaining(self) -> int:
        length = self.length
        if length < 0:
            return 1 if not self.done else 0
        return max(0, length - self.offset)

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "start": self.start,
            "end": self.end,
            "offset": self.offset,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Chunk":
        return cls(
            index=int(data.get("index", 0)),
            start=int(data.get("start", 0)),
            end=int(data.get("end", -1)),
            offset=int(data.get("offset", 0)),
        )


class HttpDownloadTask(BaseTask):
    """把单个文件切成多个区间，由多个工作线程并行下载。"""

    def __init__(self, info, save_dir: str, threads: int = 8, max_retry: int = 5, parent=None):
        super().__init__(info, save_dir, parent)
        self.threads = max(1, min(16, int(threads)))
        self.max_retry = max(0, min(10, int(max_retry)))
        self.chunks: List[Chunk] = []
        self._part_path = ""
        self._state_path = ""
        self._workers: Dict[int, threading.Thread] = {}
        self._run_event = threading.Event()
        self._stop_event = threading.Event()
        self._chunk_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._last_state_save = 0.0
        self._failed = False
        self._completed = False

    # ------------------------------------------------------------------ 路径
    @property
    def part_path(self) -> str:
        return self._part_path

    def _prepare_paths(self) -> None:
        base = sanitize_filename(self.info.name or "", default="download")
        os.makedirs(self.save_dir, exist_ok=True)
        self._part_path = os.path.join(self.save_dir, base + ".dhpart")
        self._state_path = self._part_path + ".json"

    # ------------------------------------------------------------------ 分片计划
    def _plan_chunks(self, total: int) -> List[Chunk]:
        if total <= 0 or not self.info.resumable:
            return [Chunk(index=0, start=0, end=-1 if total <= 0 else total - 1)]
        count = self.threads
        if MIN_CHUNK_SIZE > 0:
            count = max(1, min(count, max(1, total // MIN_CHUNK_SIZE)))
        step = total // count
        chunks: List[Chunk] = []
        for index in range(count):
            start = index * step
            end = total - 1 if index == count - 1 else (start + step - 1)
            chunks.append(Chunk(index=index, start=start, end=end))
        return chunks

    def _load_state(self) -> bool:
        """读取断点信息，成功恢复返回 True。"""
        if not os.path.exists(self._state_path):
            return False
        try:
            with open(self._state_path, "r", encoding="utf-8") as fp:
                data = json.load(fp)
        except (OSError, ValueError):
            return False
        if int(data.get("total", -1)) != (self.total if self.total > 0 else -1):
            return False
        if int(data.get("threads", self.threads)) <= 0:
            return False
        try:
            chunks = [Chunk.from_dict(item) for item in data.get("chunks", [])]
        except Exception:
            return False
        if not chunks:
            return False
        if not os.path.exists(self._part_path):
            return False
        self.chunks = chunks
        self.received = sum(chunk.offset for chunk in chunks)
        return True

    def _save_state(self, force: bool = False) -> None:
        if not self._state_path or self._completed:
            return
        now = time.time()
        if not force and now - self._last_state_save < 3:
            return
        self._last_state_save = now
        payload = {
            "url": self.info.url,
            "total": self.total,
            "threads": len(self.chunks),
            "chunks": [chunk.to_dict() for chunk in self.chunks],
        }
        tmp = self._state_path + ".tmp"
        try:
            with self._state_lock:
                with open(tmp, "w", encoding="utf-8") as fp:
                    json.dump(payload, fp)
                os.replace(tmp, self._state_path)
        except OSError:
            pass

    def _ensure_file(self) -> None:
        if not os.path.exists(self._part_path):
            with open(self._part_path, "wb"):
                pass
        if self.total > 0:
            current = os.path.getsize(self._part_path)
            if current != self.total:
                with open(self._part_path, "r+b") as fp:
                    fp.truncate(self.total)

    # ------------------------------------------------------------------ 生命周期
    def start(self):
        if self.state is TaskState.FINISHED:
            return
        if self.state is TaskState.DOWNLOADING and self._run_event.is_set():
            return
        self._prepare_paths()
        if not self.chunks:
            if not self._load_state():
                self.chunks = self._plan_chunks(self.total)
        self._ensure_file()
        self._failed = False
        self.error = ""
        self._stop_event.clear()
        self._run_event.set()
        self.set_state(TaskState.DOWNLOADING, self._progress_message())
        self._ensure_workers()
        # 分片可能在上一次运行中已全部完成（续传场景）
        self._check_complete()

    def pause(self):
        if self.state in (TaskState.FINISHED, TaskState.CANCELED):
            return
        self._run_event.clear()
        self._save_state(force=True)
        self.set_state(TaskState.PAUSED, "已暂停，可继续下载")

    def resume(self):
        if self.state is TaskState.FINISHED:
            return
        if self.state is TaskState.ERROR:
            self.error = ""
            self._failed = False
        self.start()

    def cancel(self, remove_files: bool = True):
        self._stop_event.set()
        self._run_event.set()
        for thread in list(self._workers.values()):
            if thread.is_alive():
                thread.join(timeout=3)
        self._workers.clear()
        if remove_files:
            for path in (self._part_path, self._state_path):
                try:
                    if path and os.path.exists(path):
                        os.remove(path)
                except OSError:
                    pass
        self.set_state(TaskState.CANCELED, "已取消")

    # ------------------------------------------------------------------ 工作线程
    def fail(self, message: str) -> None:
        """严重错误时停止所有分块线程，保留已下载部分以便续传。"""
        self._failed = True
        self._stop_event.set()
        self._run_event.set()
        self._save_state(force=True)
        super().fail(message)

    def _ensure_workers(self):
        for chunk in self.chunks:
            if chunk.remaining() <= 0:
                chunk.done = True
                continue
            worker = self._workers.get(chunk.index)
            if worker is not None and worker.is_alive():
                continue
            worker = threading.Thread(
                target=self._worker, args=(chunk,), name=f"chunk-{chunk.index}", daemon=True
            )
            self._workers[chunk.index] = worker
            worker.start()

    def _worker(self, chunk: Chunk):
        session = requests.Session()
        session.headers.update(DEFAULT_HEADERS)
        attempt = 0
        try:
            while not self._stop_event.is_set() and chunk.remaining() > 0:
                self._run_event.wait()
                if self._stop_event.is_set():
                    return
                try:
                    self._download_chunk(session, chunk)
                    if chunk.remaining() <= 0:
                        chunk.done = True
                        self._save_state(force=True)
                        self._check_complete()
                        return
                except _PauseRequested:
                    continue
                except Exception as exc:  # 网络/IO 异常 → 重试
                    if self._stop_event.is_set():
                        return
                    attempt += 1
                    if attempt > self.max_retry:
                        self.fail(f"下载失败（重试 {self.max_retry} 次仍失败）：{exc}")
                        return
                    self.message = f"连接异常，{attempt}/{self.max_retry} 次重试：{exc}"
                    self.emit_updated(force=True)
                    if self._sleep(min(2 * attempt, 10)):
                        return
                else:
                    # 本次请求成功下载，清除临时性的“连接异常”提示
                    if self.state is TaskState.DOWNLOADING and self.message.startswith("连接异常"):
                        self.message = self._progress_message()
                        self.emit_updated(force=True)
        finally:
            session.close()

    def _sleep(self, seconds: float) -> bool:
        """可中断的等待，返回 True 表示收到停止信号。"""
        return self._stop_event.wait(seconds)

    def _download_chunk(self, session: requests.Session, chunk: Chunk):
        start_pos = chunk.start + chunk.offset
        headers = dict(self.info.extra.get("headers", {}) or {})
        if self.info.resumable:
            if chunk.end >= 0:
                headers["Range"] = f"bytes={start_pos}-{chunk.end}"
            elif start_pos > 0:
                headers["Range"] = f"bytes={start_pos}-"

        response = session.get(
            self.info.url,
            headers=headers,
            stream=True,
            timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            allow_redirects=True,
        )
        try:
            if response.status_code == 416:  # 区间越界：可能已下载完
                chunk.done = True
                return
            if response.status_code >= 400:
                raise RuntimeError(f"HTTP {response.status_code}")
            if response.status_code == 200:
                # 服务器忽略了 Range 请求
                if chunk.index == 0 and chunk.offset == 0:
                    chunk.start = 0
                else:
                    raise RuntimeError("服务器不支持断点续传（未返回 206）")

            mode = "r+b" if os.path.exists(self._part_path) else "wb"
            with open(self._part_path, mode) as fp:
                fp.seek(chunk.start + chunk.offset)
                for data in response.iter_content(BLOCK_SIZE):
                    if not data:
                        continue
                    if self._stop_event.is_set():
                        return
                    if not self._run_event.is_set():
                        raise _PauseRequested()
                    fp.write(data)
                    chunk.offset += len(data)
                    self.add_bytes(len(data))
                    self._save_state()
                fp.flush()

            if chunk.end < 0:
                # 未知长度：服务器关闭连接即视为完成
                chunk.done = True
                self.total = max(self.total, self.received)
        finally:
            response.close()

    # ------------------------------------------------------------------ 完成处理
    def _check_complete(self):
        if self._stop_event.is_set() or self._failed:
            return
        for chunk in self.chunks:
            if chunk.remaining() > 0:
                return
        if self.total > 0 and self.received < self.total:
            return
        self._finalize()

    def _finalize(self):
        if self._completed:
            return
        self._completed = True
        try:
            if self.total > 0 and os.path.getsize(self._part_path) != self.total:
                with open(self._part_path, "r+b") as fp:
                    fp.truncate(self.total)
            final_path = unique_path(os.path.join(self.save_dir, self.info.name or "download"))
            os.replace(self._part_path, final_path)
            self.save_path = final_path
            if self.total <= 0:
                self.total = self.received
            self.received = self.total if self.total > 0 else self.received
        except OSError as exc:
            self.fail(f"保存文件失败：{exc}")
            return

        self._part_path = ""
        try:
            if self._state_path and os.path.exists(self._state_path):
                os.remove(self._state_path)
        except OSError:
            pass
        self.set_state(TaskState.FINISHED, "下载完成")
        self.emit_updated(force=True)
        self.finished.emit(self)

    # ------------------------------------------------------------------ 状态/序列化
    def _progress_message(self) -> str:
        if len(self.chunks) > 1:
            return f"{len(self.chunks)} 线程并行下载"
        return "单线程下载"

    def to_dict(self) -> dict:
        data = super().to_dict()
        data.update({"type": "http", "threads": self.threads})
        return data

    @classmethod
    def from_dict(cls, data: dict, threads: int = 8, max_retry: int = 5) -> "HttpDownloadTask":
        from .models import FileInfo

        info = FileInfo.from_dict(data.get("info", {}))
        task = cls(info, data.get("save_dir", ""), threads=threads, max_retry=max_retry)
        task.received = int(data.get("received", 0))
        task.save_path = data.get("save_path", "")
        return task
