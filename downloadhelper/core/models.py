"""数据模型与全局配置。"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict


class TaskState(str, Enum):
    QUEUED = "queued"
    PREPARING = "preparing"
    DOWNLOADING = "downloading"
    PAUSED = "paused"
    FINISHED = "finished"
    ERROR = "error"
    CANCELED = "canceled"


STATE_LABELS: Dict[str, str] = {
    TaskState.QUEUED: "排队中",
    TaskState.PREPARING: "获取信息",
    TaskState.DOWNLOADING: "下载中",
    TaskState.PAUSED: "已暂停",
    TaskState.FINISHED: "已完成",
    TaskState.ERROR: "出错",
    TaskState.CANCELED: "已取消",
}


def state_label(state: Any) -> str:
    key = state.value if isinstance(state, TaskState) else str(state)
    return STATE_LABELS.get(key, str(state))


class LinkKind(str, Enum):
    HTTP = "http"
    MAGNET = "magnet"
    TORRENT = "torrent"


KIND_LABELS: Dict[str, str] = {
    LinkKind.HTTP: "HTTP 多线程",
    LinkKind.MAGNET: "BT 磁力",
    LinkKind.TORRENT: "BT 种子",
}


@dataclass
class FileInfo:
    """探测到的远端文件信息，供确认弹窗展示。"""

    url: str = ""
    name: str = ""
    size: int = -1  # -1 表示未知
    mime: str = ""
    kind: LinkKind = LinkKind.HTTP
    resumable: bool = True
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "name": self.name,
            "size": self.size,
            "mime": self.mime,
            "kind": self.kind.value if isinstance(self.kind, LinkKind) else str(self.kind),
            "resumable": self.resumable,
            "extra": self.extra,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FileInfo":
        return cls(
            url=data.get("url", ""),
            name=data.get("name", ""),
            size=int(data.get("size", -1)),
            mime=data.get("mime", ""),
            kind=LinkKind(data.get("kind", "http")),
            resumable=bool(data.get("resumable", True)),
            extra=data.get("extra", {}) or {},
        )


DEFAULT_SAVE_DIR = os.path.join(os.path.expanduser("~"), "Downloads", "DownloadHelper")
APP_DIR = os.path.join(os.path.expanduser("~"), ".downloadhelper")


def ensure_app_dir() -> str:
    os.makedirs(APP_DIR, exist_ok=True)
    os.makedirs(os.path.join(APP_DIR, "torrents"), exist_ok=True)
    os.makedirs(DEFAULT_SAVE_DIR, exist_ok=True)
    return APP_DIR


def config_path() -> str:
    ensure_app_dir()
    return os.path.join(APP_DIR, "config.json")


def tasks_path() -> str:
    ensure_app_dir()
    return os.path.join(APP_DIR, "tasks.json")


@dataclass
class Config:
    save_dir: str = DEFAULT_SAVE_DIR
    threads: int = 8          # 单文件分块线程数
    max_active: int = 3       # 同时下载的文件数（需求：最多 3 个）
    max_retry: int = 5

    def clamp(self) -> "Config":
        self.threads = max(1, min(16, int(self.threads)))
        self.max_active = max(1, min(3, int(self.max_active)))
        self.max_retry = max(0, min(10, int(self.max_retry)))
        if not self.save_dir:
            self.save_dir = DEFAULT_SAVE_DIR
        return self

    def to_dict(self) -> Dict[str, Any]:
        return {
            "save_dir": self.save_dir,
            "threads": self.threads,
            "max_active": self.max_active,
            "max_retry": self.max_retry,
        }

    @classmethod
    def load(cls) -> "Config":
        try:
            with open(config_path(), "r", encoding="utf-8") as fp:
                data = json.load(fp)
        except Exception:
            return cls().clamp()
        cfg = cls(
            save_dir=data.get("save_dir", DEFAULT_SAVE_DIR),
            threads=int(data.get("threads", 8)),
            max_active=int(data.get("max_active", 3)),
            max_retry=int(data.get("max_retry", 5)),
        )
        return cfg.clamp()

    def save(self) -> None:
        try:
            with open(config_path(), "w", encoding="utf-8") as fp:
                json.dump(self.to_dict(), fp, ensure_ascii=False, indent=2)
        except OSError:
            pass
