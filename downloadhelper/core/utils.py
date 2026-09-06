"""通用工具函数：格式化、文件名处理、链接识别等。"""

from __future__ import annotations

import mimetypes
import os
import re
from urllib.parse import unquote, urlparse

from .models import LinkKind

_SIZE_UNITS = ("B", "KB", "MB", "GB", "TB", "PB")
_ILLEGAL_CHARS = re.compile(r'[\\/:*?"<>|\r\n\t]')

CATEGORY_COLORS = {
    "video": "#FF6B81",
    "audio": "#8B7CFF",
    "image": "#35D399",
    "archive": "#FFB020",
    "document": "#4C8DFF",
    "program": "#00C2FF",
    "torrent": "#FF9F43",
    "other": "#7F8CA8",
}

CATEGORY_LABELS = {
    "video": "视频",
    "audio": "音频",
    "image": "图片",
    "archive": "压缩包",
    "document": "文档",
    "program": "程序",
    "torrent": "BT 种子",
    "other": "文件",
}

_EXT_CATEGORY = {
    "video": {"mp4", "mkv", "avi", "mov", "wmv", "flv", "webm", "m4v", "ts", "mpg", "mpeg"},
    "audio": {"mp3", "flac", "wav", "aac", "m4a", "ogg", "opus", "wma"},
    "image": {"jpg", "jpeg", "png", "gif", "webp", "bmp", "svg", "heic", "tiff", "ico"},
    "archive": {"zip", "rar", "7z", "tar", "gz", "bz2", "xz", "iso", "cab", "tgz"},
    "document": {"pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt", "md", "csv", "epub", "mobi"},
    "program": {"exe", "msi", "dmg", "apk", "deb", "rpm", "pkg", "appimage", "jar"},
    "torrent": {"torrent"},
}


def format_size(num) -> str:
    """字节数 → 人类可读字符串（未知返回“未知”）。"""
    try:
        num = float(num)
    except (TypeError, ValueError):
        return "未知"
    if num < 0:
        return "未知"
    unit_index = 0
    while num >= 1024 and unit_index < len(_SIZE_UNITS) - 1:
        num /= 1024.0
        unit_index += 1
    if unit_index == 0:
        return f"{int(num)} {_SIZE_UNITS[unit_index]}"
    return f"{num:.2f} {_SIZE_UNITS[unit_index]}"


def format_speed(bps: float) -> str:
    if not bps or bps <= 0:
        return "0 B/s"
    return format_size(bps) + "/s"


def format_eta(seconds) -> str:
    try:
        seconds = int(seconds)
    except (TypeError, ValueError):
        return "--:--"
    if seconds < 0 or seconds > 99 * 3600:
        return "--:--"
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def sanitize_filename(name: str, default: str = "download") -> str:
    """清理非法字符，避免 Windows/Linux 下写文件失败。"""
    if not name:
        return default
    name = _ILLEGAL_CHARS.sub("_", name)
    name = name.strip().strip(". ")
    name = re.sub(r"\s+", " ", name)
    if len(name) > 180:
        root, ext = os.path.splitext(name)
        name = root[: 180 - len(ext)] + ext
    return name or default


def unique_path(path: str) -> str:
    """若文件已存在，追加 (1)/(2)… 避免覆盖。"""
    if not os.path.exists(path):
        return path
    root, ext = os.path.splitext(path)
    index = 1
    while os.path.exists(f"{root} ({index}){ext}"):
        index += 1
    return f"{root} ({index}){ext}"


def detect_kind(url: str) -> LinkKind:
    text = (url or "").strip()
    if text.lower().startswith("magnet:"):
        return LinkKind.MAGNET
    if text.lower().startswith("thunder://") or text.lower().startswith("ed2k://"):
        return LinkKind.MAGNET  # 不支持的协议，交给解析端报错
    path = urlparse(text).path.lower()
    if path.endswith(".torrent"):
        return LinkKind.TORRENT
    return LinkKind.HTTP


def filename_from_url(url: str) -> str:
    try:
        path = unquote(urlparse(url).path)
    except Exception:
        return ""
    name = os.path.basename(path.rstrip("/"))
    return name


def filename_from_content_disposition(value: str) -> str:
    """解析 Content-Disposition 中的 filename / filename*。"""
    if not value:
        return ""
    match = re.search(r"filename\*\s*=\s*[^']*''([^;]+)", value, re.I)
    if match:
        return unquote(match.group(1).strip('"'))
    match = re.search(r'filename\s*=\s*"([^"]+)"', value, re.I)
    if match:
        return match.group(1)
    match = re.search(r"filename\s*=\s*([^;]+)", value, re.I)
    if match:
        return match.group(1).strip().strip('"')
    return ""


def extension_of(name: str) -> str:
    ext = os.path.splitext(name)[1]
    return ext[1:].lower() if ext else ""


def guess_extension(mime: str) -> str:
    if not mime:
        return ""
    mime = mime.split(";")[0].strip()
    try:
        ext = mimetypes.guess_extension(mime) or ""
    except Exception:
        ext = ""
    return ext.lstrip(".")


def category_of(name: str, mime: str = "") -> str:
    ext = extension_of(name) or guess_extension(mime)
    for category, exts in _EXT_CATEGORY.items():
        if ext in exts:
            return category
    if mime:
        main = mime.split(";")[0].strip().lower()
        if main.startswith("video/"):
            return "video"
        if main.startswith("audio/"):
            return "audio"
        if main.startswith("image/"):
            return "image"
        if main.startswith("text/") or main == "application/pdf":
            return "document"
    return "other"


def category_color(name: str, mime: str = "") -> str:
    return CATEGORY_COLORS.get(category_of(name, mime), CATEGORY_COLORS["other"])


def category_label(name: str, mime: str = "") -> str:
    return CATEGORY_LABELS.get(category_of(name, mime), CATEGORY_LABELS["other"])
