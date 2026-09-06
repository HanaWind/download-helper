"""链接解析：HTTP 文件信息探测、种子解析、磁力元数据获取。"""

from __future__ import annotations

import os
import time
import warnings

from PySide6.QtCore import QThread, Signal

from .logging_setup import get_logger
from .models import APP_DIR, FileInfo, LinkKind, ensure_app_dir
from .utils import (
    detect_kind,
    extension_of,
    filename_from_content_disposition,
    filename_from_url,
    guess_extension,
    sanitize_filename,
)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36 HanaDownloadHelper/1.0"
    ),
    "Accept": "*/*",
    "Accept-Encoding": "identity",
}
CONNECT_TIMEOUT = 8
READ_TIMEOUT = 20

logger = get_logger()


class ProbeError(Exception):
    """链接解析失败。"""


def _parse_total_from_range(value: str):
    """从 Content-Range: bytes 0-0/1234 中解析总大小。"""
    if not value:
        return None
    try:
        return int(value.split("/")[-1])
    except (ValueError, IndexError):
        return None


def _finalize_name(url: str, candidate: str, mime: str) -> str:
    name = sanitize_filename(candidate or "", default="")
    if not name:
        name = sanitize_filename(filename_from_url(url), default="")
    if not name:
        name = "download"
    if not extension_of(name):
        ext = guess_extension(mime)
        if ext:
            name = f"{name}.{ext}"
    return name


def probe_url(url: str, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT)) -> FileInfo:
    """通过 HEAD（失败时退化为 Range GET）获取远端文件信息。"""
    import requests  # 局部导入，避免无网络环境下的导入成本

    url = (url or "").strip()
    if not url:
        raise ProbeError("链接为空")
    if not url.lower().startswith(("http://", "https://")):
        raise ProbeError("仅支持 http / https 链接")

    try:
        response = requests.head(
            url, headers=DEFAULT_HEADERS, timeout=timeout, allow_redirects=True
        )
        headers = dict(response.headers)
        status = response.status_code
        final_url = response.url
    except Exception:  # 网络异常 / 服务器不支持 HEAD
        headers, status, final_url = {}, None, url

    if status is None or status >= 400 or not headers.get("Content-Length"):
        try:
            probe_headers = dict(DEFAULT_HEADERS)
            probe_headers["Range"] = "bytes=0-0"
            response = requests.get(
                url,
                headers=probe_headers,
                timeout=timeout,
                stream=True,
                allow_redirects=True,
            )
            headers = dict(response.headers)
            status = response.status_code
            final_url = response.url
            response.close()
        except Exception as exc:
            raise ProbeError(f"无法连接服务器：{exc}") from exc

    if status >= 400:
        raise ProbeError(f"服务器返回 HTTP {status}")

    content_length = headers.get("Content-Length")
    total = int(content_length) if content_length and content_length.isdigit() else -1
    range_total = _parse_total_from_range(headers.get("Content-Range", ""))
    if range_total:
        total = range_total

    mime = headers.get("Content-Type", "").split(";")[0].strip()
    accept_ranges = headers.get("Accept-Ranges", "").lower() == "bytes"
    resumable = accept_ranges or bool(headers.get("Content-Range")) or status == 206

    kind = detect_kind(final_url)
    if kind is LinkKind.TORRENT or mime == "application/x-bittorrent":
        try:
            return probe_torrent_url(final_url)
        except ProbeError:
            pass

    name = _finalize_name(
        final_url, filename_from_content_disposition(headers.get("Content-Disposition", "")), mime
    )
    return FileInfo(
        url=final_url,
        name=name,
        size=total,
        mime=mime,
        kind=LinkKind.HTTP,
        resumable=resumable,
        extra={"accept_ranges": accept_ranges},
    )


def probe_torrent_url(url: str, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT)) -> FileInfo:
    """下载 .torrent 文件并解析出名称、大小与文件数。"""
    import requests

    response = requests.get(url, headers=DEFAULT_HEADERS, timeout=timeout)
    if response.status_code >= 400:
        raise ProbeError(f"种子下载失败：HTTP {response.status_code}")
    return parse_torrent_bytes(response.content, source=url)


def parse_torrent_bytes(data: bytes, source: str = "") -> FileInfo:
    import libtorrent as lt

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            info = lt.torrent_info(lt.bdecode(data))
        except Exception as exc:
            raise ProbeError(f"种子文件解析失败：{exc}") from exc
        name = info.name()
        size = info.total_size()
        try:
            file_count = info.num_files()
        except Exception:
            file_count = 1

    torrent_path = _store_torrent(name or "torrent", data)
    return FileInfo(
        url=source,
        name=sanitize_filename(name or "", default="torrent-download"),
        size=int(size),
        mime="application/x-bittorrent",
        kind=LinkKind.TORRENT,
        resumable=True,
        extra={"torrent_path": torrent_path, "file_count": int(file_count)},
    )


def _store_torrent(name: str, data: bytes) -> str:
    ensure_app_dir()
    import libtorrent as lt

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            info = lt.torrent_info(lt.bdecode(data))
            raw = lt.bencode(lt.create_torrent(info).generate())
            digest = str(info.info_hashes().get_best()).lower()[:24] or str(abs(hash(data)))
    except Exception:
        raw, digest = data, str(abs(hash(data)))
    path = os.path.join(APP_DIR, "torrents", f"{digest}.torrent")
    try:
        with open(path, "wb") as fp:
            fp.write(raw)
    except OSError:
        return ""
    return path


class UrlProbe(QThread):
    """在后台线程中探测 HTTP(S) 链接，避免界面卡顿。"""

    result = Signal(object)
    error = Signal(str)

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self.url = url

    def run(self):
        try:
            info = probe_url(self.url)
        except ProbeError as exc:
            logger.warning("链接解析失败：%s 原因=%s", self.url[:80], exc)
            self.error.emit(str(exc))
        except Exception as exc:  # 兜底，保证界面不会崩
            logger.exception("链接解析异常：%s", self.url[:80])
            self.error.emit(f"解析链接失败：{exc}")
        else:
            logger.info("链接解析成功：%s 名称=%s 大小=%s", self.url[:80], info.name, info.size)
            self.result.emit(info)


class MagnetProbe(QThread):
    """解析磁力链接：通过 DHT/PEX 获取元数据（文件名、大小）。"""

    result = Signal(object)
    error = Signal(str)

    def __init__(self, magnet: str, timeout: int = 90, parent=None):
        super().__init__(parent)
        self.magnet = magnet
        self.timeout = timeout
        self._handle = None
        self._canceled = False

    def cancel(self):
        self._canceled = True
        handle = self._handle
        if handle is not None:
            try:
                from .torrent_task import get_session

                get_session().remove_torrent(handle)
            except Exception:
                pass

    def run(self):
        import libtorrent as lt

        from .torrent_task import get_session

        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                params = lt.parse_magnet_uri(self.magnet)
        except Exception as exc:
            logger.warning("磁力链接格式错误：%s 原因=%s", self.magnet[:80], exc)
            self.error.emit(f"磁力链接格式错误：{exc}")
            return

        if not str(params.info_hashes.get_best()):
            self.error.emit("磁力链接缺少 btih 哈希")
            return

        try:
            session = get_session()
            params.save_path = os.path.join(APP_DIR, "torrents")
            params.flags = (
                (params.flags | lt.torrent_flags.upload_mode)
                & ~lt.torrent_flags.auto_managed
                & ~lt.torrent_flags.paused
            )
            self._handle = session.add_torrent(params)
        except Exception as exc:
            logger.error("磁力链接创建 BT 会话失败：%s 原因=%s", self.magnet[:80], exc)
            self.error.emit(f"无法创建 BT 任务：{exc}")
            return

        deadline = time.time() + self.timeout
        while time.time() < deadline:
            if self._canceled:
                return
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    status = self._handle.status()
                    if status.has_metadata:
                        info = self._handle.torrent_file()
                        name = info.name() if info else self._handle.name()
                        size = int(info.total_size()) if info else int(status.total_wanted)
                        try:
                            file_count = int(info.num_files()) if info else 1
                        except Exception:
                            file_count = 1
                        torrent_path = ""
                        if info is not None:
                            try:
                                raw = lt.bencode(lt.create_torrent(info).generate())
                                torrent_path = _store_torrent(name, raw)
                            except Exception:
                                torrent_path = ""
                        self.result.emit(
                            FileInfo(
                                url=self.magnet,
                                name=sanitize_filename(name or "", default="bt-download"),
                                size=int(size) if size else -1,
                                mime="application/x-bittorrent",
                                kind=LinkKind.MAGNET,
                                resumable=True,
                                extra={
                                    "torrent_path": torrent_path,
                                    "file_count": file_count,
                                },
                            )
                        )
                        return
            except Exception as exc:
                logger.error("磁力链接读取种子信息异常：%s 原因=%s", self.magnet[:80], exc)
                self.error.emit(f"读取种子信息失败：{exc}")
                return
            self.msleep(400)

        try:
            session.remove_torrent(self._handle)
        except Exception:
            pass
        logger.warning("磁力链接获取种子信息超时：%s", self.magnet[:80])
        self.error.emit("获取种子信息超时，请检查网络或磁力链接是否有效")
