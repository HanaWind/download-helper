"""BT / 磁力下载任务：基于 libtorrent，支持元数据获取、暂停继续与断点续传。"""

from __future__ import annotations

import os
import threading
import time
import warnings

from PySide6.QtCore import QTimer

from .base_task import BaseTask
from .models import TaskState
from .logging_setup import get_logger

logger = get_logger()

_LISTEN_PORT = 6881
_session = None
_session_lock = threading.Lock()


def get_session():
    """全局共享的 libtorrent 会话（懒加载）。"""
    global _session
    if _session is not None:
        return _session
    with _session_lock:
        if _session is not None:
            return _session
        import libtorrent as lt

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            settings = {
                "listen_interfaces": f"0.0.0.0:{_LISTEN_PORT}",
                "enable_dht": True,
                "enable_lsd": True,
                "enable_upnp": True,
                "enable_natpmp": True,
            }
            try:
                session = lt.session(settings)
            except Exception:
                session = lt.session()
            try:
                session.set_alert_mask(
                    int(
                        lt.alert.category_t.status_notification
                        | lt.alert.category_t.error_notification
                    )
                )
            except Exception:
                pass
            for router in ("router.bittorrent.com", "router.utorrent.com",
                           "dht.transmissionbt.com", "dht.libtorrent.org"):
                try:
                    session.add_dht_router(router, 6881)
                except Exception:
                    pass
            try:
                session.start_dht()
            except Exception:
                pass
        _session = session
        return _session


def _remove_handle(handle, delete_files: bool = False):
    """从会话中移除任务，可选择同时删除已下载的文件。"""
    if handle is None:
        return
    try:
        session = get_session()
    except Exception:
        return
    if delete_files:
        try:
            import libtorrent as lt

            if hasattr(lt, "remove_flags_t"):
                flag = lt.remove_flags_t.delete_files
            else:
                flag = lt.session.delete_files
            session.remove_torrent(handle, flag)
            return
        except Exception:
            pass
    try:
        session.remove_torrent(handle)
    except Exception:
        pass


class TorrentDownloadTask(BaseTask):
    """磁力链接 / 种子文件下载任务。"""

    POLL_INTERVAL = 500

    def __init__(self, info, save_dir: str, parent=None):
        super().__init__(info, save_dir, parent)
        self._handle = None
        self._timer = QTimer(self)
        self._timer.setInterval(self.POLL_INTERVAL)
        self._timer.timeout.connect(self._poll)
        self._finish_emitted = False
        self._start_ts = time.time()
        self.metadata_timeout = 180  # 磁力链接获取种子信息的最长等待（秒）

    # ------------------------------------------------------------------ 启动
    def start(self):
        import libtorrent as lt

        if self.state is TaskState.FINISHED:
            return
        if self._handle is not None and self.state is TaskState.DOWNLOADING:
            self._timer.start()
            return

        os.makedirs(self.save_dir, exist_ok=True)
        session = get_session()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            params = self._build_params(lt)
            if params is None:
                self.fail("无法解析该 BT 链接")
                return
            params.save_path = self.save_dir
            # 注意：不能设置 upload_mode（该模式只取元数据、不下载文件数据），
            # 否则磁力链接即使拿到种子信息也永远无法真正下载。
            params.flags = (
                params.flags
                & ~lt.torrent_flags.auto_managed
                & ~lt.torrent_flags.paused
                & ~lt.torrent_flags.upload_mode
            )
            self._handle = session.add_torrent(params)

        self._finish_emitted = False
        self.error = ""
        self.set_state(
            TaskState.PREPARING if self.total <= 0 else TaskState.DOWNLOADING,
            "正在连接节点…" if self.total <= 0 else "正在下载",
        )
        logger.info("BT/磁力任务启动：%s（%s）", self.info.name, self.info.url[:60])
        self._timer.start()

    def _build_params(self, lt):
        torrent_path = self.info.extra.get("torrent_path") or ""
        if torrent_path and os.path.exists(torrent_path):
            try:
                with open(torrent_path, "rb") as fp:
                    info = lt.torrent_info(lt.bdecode(fp.read()))
                params = lt.add_torrent_params()
                params.ti = info
                return params
            except Exception:
                pass
        url = (self.info.url or "").strip()
        if url.lower().startswith("magnet:"):
            try:
                return lt.parse_magnet_uri(url)
            except Exception:
                return None
        if os.path.exists(url):
            try:
                params = lt.add_torrent_params()
                params.ti = lt.torrent_info(url)
                return params
            except Exception:
                return None
        return None

    # ------------------------------------------------------------------ 轮询
    def _poll(self):
        handle = self._handle
        if handle is None:
            self._timer.stop()
            return
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                status = handle.status()
        except Exception as exc:
            self.fail(f"BT 任务异常：{exc}")
            self._timer.stop()
            return

        try:
            errc = getattr(status, "errc", None)
            if errc is not None and errc.value():
                self.message = f"节点提示：{errc.message() or 'BT 错误'}"
        except Exception:
            pass

        if not status.has_metadata:
            # 磁力链接长时间拿不到种子信息：超时后报错，避免界面一直卡在“获取种子信息”
            if self.total < 0 and time.time() - self._start_ts > self.metadata_timeout:
                logger.warning("磁力链接获取种子信息超时：%s", self.info.url[:60])
                self.fail("获取种子信息超时，请确认磁力链接有效或网络可访问 DHT")
                self._timer.stop()
                return
            self.set_state(TaskState.PREPARING, "正在获取种子信息…")
            self.emit_updated()
            return

        if self.total <= 0:
            self.total = int(status.total_wanted) or -1
        self.set_received(int(status.total_wanted_done), float(status.download_rate))
        self.message = f"节点 {status.num_peers} · 连接 {status.num_connections} · 做种 {status.num_seeds}"
        if self.state is not TaskState.DOWNLOADING and self.state is not TaskState.FINISHED:
            self.set_state(TaskState.DOWNLOADING, self.message)

        finished = bool(getattr(status, "is_finished", False)) or (
            self.total > 0 and self.received >= self.total > 0
        )
        if finished and not self._finish_emitted:
            self._finish_emitted = True
            self._on_finished(status)

    def _on_finished(self, status=None):
        self._timer.stop()
        try:
            self._handle.pause()
        except Exception:
            pass
        try:
            name = self.info.name or (self._handle.name() if self._handle else "")
        except Exception:
            name = self.info.name
        candidate = os.path.join(self.save_dir, name)
        self.save_path = candidate if os.path.exists(candidate) else self.save_dir
        if self.total > 0:
            self.received = self.total
        self.set_state(TaskState.FINISHED, "下载完成")
        logger.info("BT/磁力任务完成：%s", self.info.name)
        self.emit_updated(force=True)
        self.finished.emit(self)

    # ------------------------------------------------------------------ 控制
    def pause(self):
        if self.state in (TaskState.FINISHED, TaskState.CANCELED):
            return
        if self._handle is not None:
            try:
                self._handle.pause()
            except Exception:
                pass
        self._timer.stop()
        self.set_state(TaskState.PAUSED, "已暂停，可继续下载")

    def resume(self):
        if self.state is TaskState.FINISHED:
            return
        if self._handle is None:
            self.start()
            return
        try:
            self._handle.resume()
        except Exception:
            pass
        self.error = ""
        self.set_state(
            TaskState.DOWNLOADING if self.total > 0 else TaskState.PREPARING, "正在下载"
        )
        self._timer.start()

    def cancel(self, remove_files: bool = True):
        self._timer.stop()
        _remove_handle(self._handle, delete_files=remove_files)
        self._handle = None
        self.set_state(TaskState.CANCELED, "已取消")

    # ------------------------------------------------------------------ 序列化
    def to_dict(self) -> dict:
        data = super().to_dict()
        data["type"] = "torrent"
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "TorrentDownloadTask":
        from .models import FileInfo

        info = FileInfo.from_dict(data.get("info", {}))
        task = cls(info, data.get("save_dir", ""))
        task.received = int(data.get("received", 0))
        task.save_path = data.get("save_path", "")
        return task
