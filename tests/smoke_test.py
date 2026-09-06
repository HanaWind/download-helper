"""冒烟测试：本地 HTTP 服务器 + 多线程下载/断点续传 + 种子解析 + 界面截图。

运行：.venv\\Scripts\\python tests\\smoke_test.py
"""

from __future__ import annotations

import hashlib
import os
import shutil
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from downloadhelper.core import Config, FileInfo, LinkKind  # noqa: E402
from downloadhelper.core.http_task import HttpDownloadTask  # noqa: E402
from downloadhelper.core.manager import DownloadManager  # noqa: E402
from downloadhelper.core.models import TaskState  # noqa: E402
from downloadhelper.core.probe import parse_torrent_bytes, probe_url  # noqa: E402

FILE_SIZE = 8 * 1024 * 1024
SERVE_DIR = tempfile.mkdtemp(prefix="dh_serve_")
FILE_PATH = os.path.join(SERVE_DIR, "bigfile.bin")
# 限速，便于观察暂停/继续过程（全局约 6 MB/s）
RATE = 6 * 1024 * 1024
BLOCK = 128 * 1024
_rate_lock = threading.Lock()
_rate_state = {"last": time.perf_counter(), "budget": 0.0}


def throttle(count: int) -> float:
    """全局令牌桶限速（允许负债，保证多连接下总速度不超过 RATE）。"""
    with _rate_lock:
        now = time.perf_counter()
        _rate_state["budget"] = min(
            _rate_state["budget"] + (now - _rate_state["last"]) * RATE, RATE * 0.5
        )
        _rate_state["last"] = now
        _rate_state["budget"] -= count
    return max(0.0, -_rate_state["budget"] / RATE)


def prepare_file():
    with open(FILE_PATH, "wb") as fp:
        fp.write(os.urandom(FILE_SIZE))


class RangeHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def _file_data(self):
        with open(FILE_PATH, "rb") as fp:
            return fp.read()

    def _send(self, body: bytes, status: int = 200, headers: dict = None, head_only: bool = False):
        self.send_response(status)
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        if "Content-Length" not in (headers or {}):
            self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if not head_only and body:
            position = 0
            while position < len(body):
                chunk = body[position:position + BLOCK]
                self.wfile.write(chunk)
                position += len(chunk)
                wait = throttle(len(chunk))
                if wait:
                    time.sleep(wait)

    def do_HEAD(self):
        self._send(b"", 200, {
            "Content-Type": "application/octet-stream",
            "Accept-Ranges": "bytes",
            "Content-Length": str(FILE_SIZE),
            "Content-Disposition": 'attachment; filename="bigfile.bin"',
        })

    def do_GET(self):
        data = self._file_data()
        total = len(data)
        rng = self.headers.get("Range")
        if rng:
            start_text, _, end_text = rng.replace("bytes=", "").partition("-")
            start = int(start_text)
            end = int(end_text) if end_text else total - 1
            end = min(end, total - 1)
            body = data[start:end + 1]
            self._send(body, 206, {
                "Content-Type": "application/octet-stream",
                "Accept-Ranges": "bytes",
                "Content-Range": f"bytes {start}-{end}/{total}",
            })
            return
        self._send(data, 200, {"Content-Type": "application/octet-stream"})


def start_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), RangeHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_address[1]}/bigfile.bin"


def md5(path: str) -> str:
    digest = hashlib.md5()
    with open(path, "rb") as fp:
        for block in iter(lambda: fp.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def wait_until(predicate, timeout: float = 90.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        QApplication.processEvents()
        if predicate():
            return True
        time.sleep(0.02)
    return False


def pump(app, seconds: float):
    deadline = time.time() + seconds
    while time.time() < deadline:
        app.processEvents()
        time.sleep(0.02)


def check(results, name: str, ok: bool, detail: str = ""):
    results.append((name, ok, detail))
    print(("[PASS] " if ok else "[FAIL] ") + name + (f" - {detail}" if detail else ""))


def test_probe_and_download(app, url: str, results):
    info = probe_url(url)
    check(results, "probe: 文件大小正确", info.size == FILE_SIZE, f"{info.size}")
    check(results, "probe: 文件名解析", info.name == "bigfile.bin", info.name)
    check(results, "probe: 支持断点续传", info.resumable)

    save_dir = tempfile.mkdtemp(prefix="dh_dl_")
    task = HttpDownloadTask(info, save_dir, threads=4)
    finished = []

    def on_finished(t):
        finished.append(t)

    task.finished.connect(on_finished)
    task.start()
    ok = wait_until(lambda: task.state is TaskState.FINISHED, 60)
    check(results, "多线程下载完成", ok, f"{task.state} {task.error} {task.message}".strip())
    if ok:
        expected = os.path.join(save_dir, "bigfile.bin")
        check(results, "文件保存路径正确", os.path.exists(expected), expected)
        check(results, "文件校验一致", md5(expected) == md5(FILE_PATH))
        check(results, "临时文件已清理",
              not any(p.endswith(".dhpart") or p.endswith(".json")
                      for p in os.listdir(save_dir)), str(os.listdir(save_dir)))
    shutil.rmtree(save_dir, ignore_errors=True)


def test_pause_resume(app, url: str, results):
    info = probe_url(url)
    save_dir = tempfile.mkdtemp(prefix="dh_resume_")
    task = HttpDownloadTask(info, save_dir, threads=2)
    task.start()
    ok = wait_until(lambda: task.received > 300 * 1024, 30)
    check(results, "暂停前已下载部分数据", ok, f"{task.received} bytes")
    task.pause()
    pump(app, 0.6)
    paused_bytes = task.received
    pump(app, 1.0)
    check(results, "暂停后不再写入", task.received == paused_bytes,
          f"{paused_bytes} -> {task.received}")
    check(results, "暂停状态正确", task.state is TaskState.PAUSED, str(task.state))
    saved = [p for p in os.listdir(save_dir) if p.endswith(".dhpart.json")]
    check(results, "断点信息已保存", bool(saved), str(os.listdir(save_dir)))
    task.resume()
    ok = wait_until(lambda: task.state is TaskState.FINISHED, 60)
    check(results, "继续后下载完成", ok, f"{task.state} {task.error} {task.message}".strip())
    if ok:
        target = os.path.join(save_dir, "bigfile.bin")
        check(results, "续传文件校验一致", md5(target) == md5(FILE_PATH))
    shutil.rmtree(save_dir, ignore_errors=True)


def test_concurrency(app, url: str, results):
    config = Config(threads=4, max_active=3)
    config.save_dir = tempfile.mkdtemp(prefix="dh_multi_")
    manager = DownloadManager(config)
    info = probe_url(url)
    tasks = []
    for index in range(5):
        task_info = FileInfo(url=url, name=f"file_{index}.bin", size=info.size,
                             mime="application/octet-stream", kind=LinkKind.HTTP,
                             resumable=True)
        tasks.append(manager.add_task(task_info, config.save_dir))
    pump(app, 1.0)
    active = len([t for t in manager.tasks if t.is_active])
    detail = str([(t.state.value, int(t.percent)) for t in manager.tasks])
    check(results, "同时下载数量不超过 3", active <= 3, f"active={active} {detail}")
    check(results, "并发任务达到上限 3", active == 3, f"active={active} {detail}")

    max_active = active
    deadline = time.time() + 300
    while time.time() < deadline and not all(t.state is TaskState.FINISHED for t in tasks):
        pump(app, 0.2)
        max_active = max(max_active, len([t for t in manager.tasks if t.is_active]))
    ok = all(t.state is TaskState.FINISHED for t in tasks)
    check(results, "全程并发未超过 3", max_active <= 3, f"max={max_active}")
    check(results, "5 个任务全部完成", ok,
          str([(t.state.value, t.error) for t in tasks]))
    if ok:
        check(results, "全部文件校验一致",
              all(md5(t.save_path) == md5(FILE_PATH) for t in tasks))
    shutil.rmtree(config.save_dir, ignore_errors=True)


def test_torrent_parse(results):
    import libtorrent as lt

    work = tempfile.mkdtemp(prefix="dh_torrent_")
    payload = os.path.join(work, "movie.mkv")
    with open(payload, "wb") as fp:
        fp.write(os.urandom(200000))

    fs = lt.file_storage()
    lt.add_files(fs, payload)
    creator = lt.create_torrent(fs)
    lt.set_piece_hashes(creator, work)
    raw = lt.bencode(creator.generate())

    info = parse_torrent_bytes(raw, source="memory")
    check(results, "种子解析：文件名", info.name == "movie.mkv", info.name)
    check(results, "种子解析：大小", info.size == 200000, str(info.size))
    check(results, "种子解析：类型", info.kind is LinkKind.TORRENT)
    shutil.rmtree(work, ignore_errors=True)


def test_magnet_probe(app, results):
    """磁力链接元数据获取失败时应给出明确提示（离线环境验证超时分支）。"""
    from downloadhelper.core.probe import MagnetProbe

    magnet = "magnet:?xt=urn:btih:0123456789abcdef0123456789abcdef01234567&dn=demo"
    probe = MagnetProbe(magnet, timeout=5)
    errors = []
    probe.error.connect(errors.append)
    probe.start()
    ok = wait_until(lambda: bool(errors), 25)
    check(results, "磁力解析：超时给出提示", ok and "超时" in errors[0], str(errors[:1]))
    probe.wait(3000)


def test_ui(app, url: str, results):
    from downloadhelper.ui.main_window import MainWindow

    window = MainWindow()
    for task in list(window.manager.tasks):
        window.manager.remove_task(task.id)
    window.resize(1040, 700)
    window.show()
    pump(app, 0.4)

    info = probe_url(url)
    save_dir = window.config.save_dir
    os.makedirs(save_dir, exist_ok=True)
    first = window.manager.add_task(info, save_dir)
    second_info = FileInfo(url=url, name="演示-暂停任务.bin", size=info.size,
                           mime="application/octet-stream", kind=LinkKind.HTTP,
                           resumable=True)
    second = window.manager.add_task(second_info, save_dir)
    window.manager.add_task(
        FileInfo(url="magnet:?xt=urn:btih:0123456789abcdef0123456789abcdef01234567",
                 name="演示-BT磁力任务.mkv", size=-1, mime="application/x-bittorrent",
                 kind=LinkKind.MAGNET), save_dir)
    pump(app, 1.2)
    second.pause()
    pump(app, 0.4)

    check(results, "界面：任务卡片数量", len(window._cards) == 3, str(len(window._cards)))
    out_dir = os.path.join(ROOT, "tests")
    os.makedirs(out_dir, exist_ok=True)
    shot = os.path.join(out_dir, "preview_main.png")
    window.grab().save(shot)
    check(results, "界面：主窗口截图", os.path.exists(shot), shot)

    from downloadhelper.ui.info_dialog import FileInfoDialog

    dialog = FileInfoDialog(info, save_dir, threads=window.config.threads, parent=window)
    dialog.show()
    pump(app, 0.3)
    shot_dialog = os.path.join(out_dir, "preview_dialog.png")
    dialog.grab().save(shot_dialog)
    check(results, "界面：信息弹窗截图", os.path.exists(shot_dialog), shot_dialog)
    dialog.reject()

    for task in list(window.manager.tasks):
        window.manager.remove_task(task.id, delete_files=True)
    window.close()


def main():
    prepare_file()
    app = QApplication.instance() or QApplication(sys.argv)
    from downloadhelper.ui.theme import QSS

    app.setStyleSheet(QSS)

    server, url = start_server()
    results = []
    try:
        test_probe_and_download(app, url, results)
        test_pause_resume(app, url, results)
        test_concurrency(app, url, results)
        test_torrent_parse(results)
        test_magnet_probe(app, results)
        test_ui(app, url, results)
    finally:
        server.shutdown()
        shutil.rmtree(SERVE_DIR, ignore_errors=True)

    failed = [item for item in results if not item[1]]
    print("\n" + "=" * 56)
    print(f"总计 {len(results)} 项，通过 {len(results) - len(failed)} 项，失败 {len(failed)} 项")
    for name, _, detail in failed:
        print(f"  - {name} {detail}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
