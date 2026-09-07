# Hana Download Helper

仿 Internet Download Manager 的 Python 下载器：多线程分块下载 + BT/磁力下载 + 断点续传，配备现代化深色/浅色可切换的 PySide6 界面。

## 功能特性

| 需求 | 实现方式 |
| --- | --- |
| 多线程并行下载同一文件 | HTTP 任务按 `Range` 把文件切成 N 段（默认 8 线程），每段独立连接、独立写入同一文件的不同偏移 |
| 最多 3 个文件同时下载 | `DownloadManager` 调度队列，正在下载数 < 上限时才启动下一个任务，其余排队等待 |
| BT 磁力下载 | 基于 `libtorrent`（libtorrent-rasterbar 官方 Python 绑定），并行利用显式 Tracker、DHT、PEX、LSD 获取 metadata，自动处理节点发现与分片校验 |
| 超时 / 异常捕获 | HTTP 连接 10s、读取 30s 超时；磁力 metadata 最长等待 30s；连接中断自动退避重试（默认 5 次），失败会显示具体原因并保留已下载分片 |
| 断点续传 | 每个分片进度写入 `<file>.dhpart.json`，暂停或退出后再次继续时从断点偏移续传 |
| 暂停 / 继续 | 暂停时中断连接并保存分片进度；继续时重建工作线程并请求剩余区间 |
| 文件信息获取 | `HEAD` 请求（必要时退化为 `Range: bytes=0-0`）解析 `Content-Length`、`Content-Disposition`、`Content-Type`、`Accept-Ranges`，磁力链接通过 DHT 获取元数据 |
| 现代化 UI | 无边框窗口 + 自定义标题栏 + 圆角阴影 + 渐变进度条，链接框回车/点击确定 → 文件信息弹窗（大小/格式/文件名）→ 确认开始下载，卡片支持暂停/继续/重试/删除/打开目录 |

## 环境要求

- Python **3.9 ~ 3.13**（`libtorrent` 官方 wheel 暂未提供 3.14 版本）
- 依赖：`PySide6`、`requests`、`libtorrent`

## 安装与运行

```bat
cd DownloadHelper

:: 1) 创建虚拟环境（以 Python 3.11 为例，3.12/3.13 亦可）
py -3.11 -m venv .venv

:: 2) 安装依赖
.venv\Scripts\python -m pip install -r requirements.txt

:: 3) 启动
.venv\Scripts\python main.py
```

> 若 `pip` 使用国内镜像导致 `libtorrent` 安装失败，可加 `-i https://pypi.org/simple` 从官方源安装。

PyCharm 用户：把项目解释器切换到 `.venv\Scripts\python.exe`，运行 `main.py` 即可。

## 使用说明

1. 顶部输入框粘贴链接（HTTP/HTTPS 直链、磁力链 `magnet:?xt=...`、`.torrent` 文件链接），按回车或点击“确定”；
2. 弹出“文件信息”窗口，展示文件大小、格式、下载方式与保存位置，可修改文件名与目录；
3. 点击“开始下载”加入任务列表（取消则不下载）；
4. 任务卡片提供：暂停 / 继续、出错重试、删除任务、打开文件所在目录；
5. 右上角齿轮可进入“下载设置”和“外观设置”，分别修改保存目录、线程、并发、重试、主题、背景图、不透明度和高斯模糊；外观滑块支持实时预览，取消会恢复原设置。

磁力链接会优先使用链接内的 Tracker，并同时启用 DHT、PEX、LSD；30 秒内未获得 metadata 会弹窗说明是未发现节点、无 peer 或节点未返回 metadata。BT 多文件任务完成后会校验本地根目录并支持打开整个任务目录。

任务列表与配置保存在 `~/.downloadhelper/`（`config.json`、`tasks.json`、磁力元数据 `torrents/`），关闭程序会自动暂停并保存进度，下次启动自动继续。

## 目录结构

```
DownloadHelper/
├─ main.py                     # 启动入口
├─ requirements.txt
├─ downloadhelper/
│  ├─ core/
│  │  ├─ models.py             # 任务状态、文件信息、配置
│  │  ├─ utils.py              # 大小/速度格式化、文件名清理、文件分类
│  │  ├─ base_task.py          # 任务基类（进度、速度滑动窗口、信号）
│  │  ├─ probe.py              # 链接解析：HTTP 探测 / 种子解析 / 磁力元数据
│  │  ├─ http_task.py          # 多线程分块下载、断点续传、暂停继续
│  │  ├─ torrent_task.py       # libtorrent 会话与 BT 任务
│  │  └─ manager.py            # 并发调度（≤3）、速度统计、持久化
│  └─ ui/
│     ├─ theme.py / icons.py   # QSS 主题与可着色 SVG 图标
│     ├─ base.py               # 无边框窗口、标题栏、阴影容器
│     ├─ info_dialog.py        # 文件信息确认弹窗
│     ├─ settings_dialog.py    # 下载设置弹窗
│     ├─ task_card.py          # 任务卡片
│     └─ main_window.py        # 主窗口与整体流程
└─ tests/smoke_test.py         # 冒烟测试（下载/续传/并发/种子解析/界面）
```

## 测试

```bat
.venv\Scripts\python tests\smoke_test.py
```

测试会启动带限速与 Range 支持的本地 HTTP 服务器，校验：

- 文件信息探测（大小、文件名、是否支持续传）
- 多线程下载结果 MD5 与源文件一致、临时文件清理
- 暂停后不再写入、断点信息落盘、继续后文件完整
- 5 个任务并发时同时下载数 ≤ 3 且全部完成
- 种子文件解析（名称/大小）
- 主窗口与信息弹窗可正常构建（输出 `tests/preview_main.png`、`tests/preview_dialog.png`）

## 常见问题

- **磁力链接一直“正在获取种子信息”**：需要能连上 DHT/Tracker 网络，热点稀少时需等待；可点击输入框右侧的 × 取消。
- **服务器不支持断点续传**：弹窗会提示，此时按单线程下载，暂停后需重新开始。
- **提示缺少 libtorrent**：请确认解释器版本 ≤ 3.13，并执行 `.venv\Scripts\python -m pip install libtorrent`。
