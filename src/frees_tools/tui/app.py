"""Keyboard-accessible TUI; processing is delegated to shared services and tasks."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable

from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Checkbox,
    ContentSwitcher,
    DataTable,
    Footer,
    Input,
    Label,
    ListItem,
    ListView,
    ProgressBar,
    Select,
    Static,
    TextArea,
)

LOGO = r""" _____ ____  _____ _____ ____    _____ ___   ___  _     ____
|  ___|  _ \| ____| ____/ ___|  |_   _/ _ \ / _ \| |   / ___|
| |_  | |_) |  _| |  _| \___ \    | || | | | | | | |   \___ \
|  _| |  _ <| |___| |___ ___) |   | || |_| | |_| | |___ ___) |
|_|   |_| \_\_____|_____|____/    |_| \___/ \___/|_____|____/"""
PAGES = [
    ("dashboard", "Dashboard / 仪表盘"),
    ("torrent", "Torrent / 种子下载"),
    ("image", "Image / 图片转换"),
    ("video", "Video / 视频转换"),
    ("pdf", "PDF / 合成工具"),
    ("tasks", "Tasks / 任务中心"),
    ("settings", "Settings / 设置"),
    ("about", "About / 帮助"),
]


class Confirm(ModalScreen[bool]):
    BINDINGS = [("escape", "reject", "返回")]

    def __init__(self, message: str):
        super().__init__()
        self.message = message

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Static(self.message, markup=False)
            with Horizontal(classes="buttons"):
                yield Button("确认", id="yes", variant="error")
                yield Button("返回", id="no")

    @on(Button.Pressed)
    def answer(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "yes")

    def action_reject(self) -> None:
        self.dismiss(False)


class Detail(ModalScreen[None]):
    BINDINGS = [("escape", "close", "关闭")]

    def __init__(self, title: str, value: object):
        super().__init__()
        self.title_text = title
        self.value = value

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog detail"):
            yield Label(self.title_text)
            yield TextArea(
                json.dumps(self.value, ensure_ascii=False, indent=2, default=str), read_only=True
            )
            yield Button("关闭", id="close-detail")

    @on(Button.Pressed)
    def close_button(self) -> None:
        self.dismiss(None)

    def action_close(self) -> None:
        self.dismiss(None)


class FileBrowser(ModalScreen[list[str] | None]):
    """Real directory browser with explicit ordered multi-selection."""

    BINDINGS = [("escape", "close", "取消"), ("backspace", "parent", "上级目录")]

    def __init__(
        self, start: str | Path | None = None, *, multiple: bool = False, directory: bool = False
    ):
        super().__init__()
        initial = Path(start or Path.cwd()).expanduser()
        self.current = initial if initial.is_dir() else initial.parent
        self.multiple = multiple
        self.directory = directory
        self.selected: list[Path] = []
        self.entries: list[Path] = []

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog browser"):
            yield Label("文件浏览器 · Enter 进入目录 / 选择文件 · Esc 返回")
            yield Input(str(self.current), id="browser-path")
            with Horizontal(classes="buttons"):
                yield Button("打开路径", id="browser-go")
                yield Button("上级目录", id="browser-parent")
                yield Button("选当前目录", id="browser-directory", disabled=not self.directory)
            yield ListView(id="browser-files")
            yield Label("已选文件（按下方顺序合成，可上移 / 下移）")
            yield ListView(id="browser-selected")
            with Horizontal(classes="buttons"):
                yield Button("上移", id="browser-up")
                yield Button("下移", id="browser-down")
                yield Button("移除", id="browser-remove")
                yield Button("使用选择", id="browser-use", variant="primary")
                yield Button("取消", id="browser-cancel")
            yield Static("", id="browser-error", markup=False)

    async def on_mount(self) -> None:
        await self.refresh_files()

    async def refresh_files(self) -> None:
        listing = self.query_one("#browser-files", ListView)
        await listing.clear()
        try:
            self.entries = sorted(
                self.current.iterdir(), key=lambda p: (not p.is_dir(), p.name.casefold())
            )
            if self.directory:
                self.entries = [p for p in self.entries if p.is_dir()]
            self.query_one("#browser-path", Input).value = str(self.current)
            await listing.extend(
                ListItem(Label(("[DIR] " if p.is_dir() else "      ") + p.name, markup=False))
                for p in self.entries
            )
            self.query_one("#browser-error", Static).update("")
        except OSError as error:
            self.entries = []
            self.query_one("#browser-error", Static).update(str(error))

    async def refresh_selected(self) -> None:
        listing = self.query_one("#browser-selected", ListView)
        await listing.clear()
        await listing.extend(ListItem(Label(str(p), markup=False)) for p in self.selected)

    @on(ListView.Selected, "#browser-files")
    async def choose(self, event: ListView.Selected) -> None:
        if event.list_view.index is None or event.list_view.index >= len(self.entries):
            return
        path = self.entries[event.list_view.index]
        if path.is_dir():
            self.current = path
            await self.refresh_files()
        else:
            if not self.multiple:
                self.selected = [path]
            elif path not in self.selected:
                self.selected.append(path)
            else:
                self.selected.remove(path)
            await self.refresh_selected()

    async def action_parent(self) -> None:
        self.current = self.current.parent
        await self.refresh_files()

    def action_close(self) -> None:
        self.dismiss(None)

    @on(Input.Submitted, "#browser-path")
    async def open_typed(self) -> None:
        await self.go_path()

    async def go_path(self) -> None:
        path = Path(self.query_one("#browser-path", Input).value).expanduser()
        if path.is_dir():
            self.current = path
            await self.refresh_files()
        elif path.is_file() and not self.directory:
            self.selected = [path]
            await self.refresh_selected()
        else:
            self.query_one("#browser-error", Static).update("路径不存在或无法读取")

    @on(Button.Pressed)
    async def buttons(self, event: Button.Pressed) -> None:
        name = event.button.id
        if name == "browser-go":
            await self.go_path()
        elif name == "browser-parent":
            await self.action_parent()
        elif name == "browser-directory":
            self.selected = [self.current]
            await self.refresh_selected()
        elif name in {"browser-up", "browser-down", "browser-remove"}:
            listing = self.query_one("#browser-selected", ListView)
            index = listing.index
            if index is not None and index < len(self.selected):
                target = index + (-1 if name == "browser-up" else 1)
                if name == "browser-remove":
                    self.selected.pop(index)
                elif 0 <= target < len(self.selected):
                    self.selected[index], self.selected[target] = (
                        self.selected[target],
                        self.selected[index],
                    )
                await self.refresh_selected()
                if self.selected:
                    listing.index = min(max(target, 0), len(self.selected) - 1)
        elif name == "browser-use":
            if self.selected:
                self.dismiss([str(p) for p in self.selected])
            else:
                self.query_one("#browser-error", Static).update("请先选择文件或目录")
        elif name == "browser-cancel":
            self.dismiss(None)


class FreesToolsApp(App):
    TITLE = "Frees Tools"
    CSS = """
    Screen { background: #0b1220; color: #e2e8f0; }
    #logo { color: #22d3ee; height: auto; padding: 1 2; text-style: bold; }
    #layout { height: 1fr; }
    #nav { width: 28; background: #111e30; border-right: solid #155e75; }
    #nav ListItem { padding: 1; height: auto; }
    ContentSwitcher { width: 1fr; padding: 1 2; }
    .page { padding: 0 1; }
    .heading { color: #22d3ee; text-style: bold; margin-bottom: 1; }
    Input, Select, TextArea { margin-bottom: 1; }
    .buttons { height: auto; min-height: 3; margin-bottom: 1; }
    .buttons Button { margin-right: 1; min-width: 8; }
    .options { height: auto; }
    .options > * { width: 1fr; margin-right: 1; }
    DataTable { height: 12; margin-bottom: 1; }
    #task-progress { margin-bottom: 1; }
    #task-selected { height: 5; overflow: hidden; }
    #pdf-inputs { height: 7; }
    #status { height: auto; max-height: 3; color: #67e8f9; padding: 0 2; }
    ModalScreen { align: center middle; background: #000000 65%; }
    .dialog { width: 80%; height: auto; max-height: 95%; padding: 1 2;
              background: #111e30; border: thick #0891b2; }
    .detail { height: 80%; }
    .detail TextArea { height: 1fr; }
    .browser { height: 90%; }
    #browser-files { height: 1fr; min-height: 4; border: solid #155e75; }
    #browser-selected { height: 5; border: solid #155e75; }
    #browser-error { color: #fb7185; height: auto; }
    """
    BINDINGS = [
        ("ctrl+q", "quit", "退出"),
        ("f1", "help", "帮助"),
        ("ctrl+t", "tasks", "任务"),
        ("escape", "dashboard", "首页"),
    ]

    def __init__(self, manager=None):
        super().__init__()
        from frees_tools.core.config import load_config
        from frees_tools.core.tasks import TaskManager

        self.config = load_config()
        self.manager = manager or TaskManager()
        self.pdf_paths: list[str] = []
        self.image_paths: list[str] = []
        self.task_id: str | None = None
        self.torrent_id: str | None = None
        self.torrent_service = None
        self.torrent_rows: list[dict] = []

    def compose(self) -> ComposeResult:
        yield Static(LOGO + "\n v0.1.0  |  Your Ultimate Terminal Toolbox", id="logo", markup=False)
        with Horizontal(id="layout"):
            yield ListView(
                *(ListItem(Label(title), id=f"nav-{name}") for name, title in PAGES), id="nav"
            )
            with ContentSwitcher(initial="dashboard", id="pages"):
                with VerticalScroll(id="dashboard", classes="page"):
                    yield Label("欢迎使用 Frees Tools", classes="heading")
                    yield Static(
                        "图片、PDF、视频和 BitTorrent，共用可靠的任务中心。\n\n"
                        "使用左侧导航进入工具。Tab 切换焦点，方向键选择，Enter 确认。\n"
                        "文件保持原样，覆盖输出需显式勾选。耗时操作在后台运行。\n\n"
                        "视频需要 FFmpeg，下载需要 aria2c；缺失时会显示安装建议。"
                    )
                    yield Button("查看当前任务", id="dashboard-tasks", variant="primary")
                    yield Static("", id="dashboard-summary")
                with VerticalScroll(id="image", classes="page"):
                    yield Label("图片转换 · 单张 / 批量", classes="heading")
                    yield Input(placeholder="输入图片路径（批量可选择多个文件）", id="image-source")
                    with Horizontal(classes="buttons"):
                        yield Button("选择图片", id="image-browse")
                        yield Button("查看信息", id="image-info")
                    yield Input(
                        placeholder="输出文件或批量输出目录（留空使用默认）", id="image-output"
                    )
                    yield Button("选择输出目录", id="image-out-browse")
                    with Horizontal(classes="options"):
                        yield Select(
                            [(x.upper(), x) for x in ("png", "jpg", "webp", "bmp", "tiff", "gif")],
                            value=self.config.get("image_format", "png"),
                            allow_blank=False,
                            id="image-format",
                        )
                        yield Input("90", placeholder="质量 1–100", id="image-quality")
                    with Horizontal(classes="options"):
                        yield Input(placeholder="宽度（留空自动）", id="image-width")
                        yield Input(placeholder="高度（留空自动）", id="image-height")
                        yield Input(placeholder="缩放百分比", id="image-scale")
                    yield Input("#ffffff", placeholder="JPEG 透明背景填充色", id="image-background")
                    yield Checkbox("显式允许覆盖已有输出", id="image-overwrite")
                    yield Checkbox(
                        "仅转换动画 / 多页文件的第一帧（会丢弃其他帧）", id="image-first"
                    )
                    yield Button("开始图片转换", id="image-start", variant="primary")
                with VerticalScroll(id="video", classes="page"):
                    yield Label("视频转换 / 音频提取", classes="heading")
                    yield Input(placeholder="输入视频文件", id="video-source")
                    with Horizontal(classes="buttons"):
                        yield Button("选择视频", id="video-browse")
                        yield Button("查看媒体信息", id="video-info")
                    yield Input(placeholder="输出文件路径（必填）", id="video-output")
                    with Horizontal(classes="options"):
                        yield Select(
                            [
                                (x.upper(), x)
                                for x in ("mp4", "mov", "mkv", "webm", "mp3", "wav", "flac", "aac")
                            ],
                            value="mp4",
                            allow_blank=False,
                            id="video-format",
                        )
                        yield Select(
                            [
                                (label, value)
                                for label, value in [
                                    ("平衡", "balanced"),
                                    ("高质量", "high-quality"),
                                    ("小体积", "small"),
                                    ("快速", "fast"),
                                ]
                            ],
                            value=self.config.get("video_preset", "balanced"),
                            allow_blank=False,
                            id="video-preset",
                        )
                    with Horizontal(classes="options"):
                        yield Input(placeholder="编码器（留空自动）", id="video-codec")
                        yield Input(placeholder="质量 CRF（可选）", id="video-quality")
                    with Horizontal(classes="options"):
                        yield Input(placeholder="分辨率，例如 1280x720", id="video-resolution")
                        yield Input(placeholder="帧率（可选）", id="video-fps")
                        yield Input("192k", placeholder="音频码率", id="video-bitrate")
                    yield Checkbox("保留音频", value=True, id="video-audio")
                    yield Checkbox("启用硬件加速（须运行时支持）", id="video-hardware")
                    yield Checkbox("显式允许覆盖已有输出", id="video-overwrite")
                    yield Button("开始转换 / 提取", id="video-start", variant="primary")
                with VerticalScroll(id="pdf", classes="page"):
                    yield Label("PDF / 图片混合合成 · 顺序即页面顺序", classes="heading")
                    yield ListView(id="pdf-inputs")
                    with Horizontal(classes="buttons"):
                        yield Button("添加文件", id="pdf-browse")
                        yield Button("上移", id="pdf-up")
                        yield Button("下移", id="pdf-down")
                        yield Button("移除", id="pdf-remove")
                        yield Button("信息", id="pdf-info")
                    yield Input(placeholder="粘贴文件路径后按 Enter 添加", id="pdf-path")
                    yield Input(placeholder="输出 PDF 文件路径（必填）", id="pdf-output")
                    with Horizontal(classes="options"):
                        yield Select(
                            [(x, x.lower()) for x in ("Auto", "A4", "A3", "Letter")],
                            value="auto",
                            allow_blank=False,
                            id="pdf-paper",
                        )
                        yield Select(
                            [("完整适应", "contain"), ("铺满裁剪", "cover")],
                            value="contain",
                            allow_blank=False,
                            id="pdf-fit",
                        )
                    yield Checkbox("显式允许覆盖已有输出", id="pdf-overwrite")
                    yield Button("开始合成 PDF", id="pdf-start", variant="primary")
                with VerticalScroll(id="torrent", classes="page"):
                    yield Label("BitTorrent 下载 · aria2 本机安全 RPC", classes="heading")
                    yield Input(placeholder="Magnet 链接或本地 .torrent 路径", id="torrent-source")
                    with Horizontal(classes="buttons"):
                        yield Button("选择种子", id="torrent-browse")
                        yield Button("选择下载目录", id="torrent-dir-browse")
                    yield Input(
                        str(self.config.get("download_dir", Path.home() / "Downloads")),
                        id="torrent-directory",
                    )
                    yield Input(
                        placeholder="选择文件编号，例如 1,3,5（留空全部；详情查看元数据）",
                        id="torrent-files",
                    )
                    yield Button("添加下载", id="torrent-add", variant="primary")
                    yield DataTable(id="torrent-table", cursor_type="row")
                    with Horizontal(classes="buttons"):
                        yield Button("刷新", id="torrent-refresh")
                        yield Button("详情 / 文件", id="torrent-details")
                        yield Button("暂停", id="torrent-pause")
                        yield Button("恢复", id="torrent-resume")
                        yield Button("重试", id="torrent-retry")
                    yield Checkbox(
                        "删除时同时删除已下载数据（需要二次确认）", id="torrent-delete-data"
                    )
                    yield Button("删除所选任务", id="torrent-remove", variant="error")
                    yield Static("下载引擎保留恢复记录；关闭界面后策略见设置与发行说明。")
                with VerticalScroll(id="tasks", classes="page"):
                    yield Label("任务中心 · 切换页面不影响任务", classes="heading")
                    yield DataTable(id="task-table", cursor_type="row")
                    yield ProgressBar(total=100, id="task-progress")
                    yield Static(
                        "选择任务查看进度、输入输出与错误", id="task-selected", markup=False
                    )
                    with Horizontal(classes="buttons"):
                        yield Button("详情 / 错误", id="task-details")
                        yield Button("取消任务", id="task-cancel", variant="error")
                        yield Button("重试失败任务", id="task-retry")
                with VerticalScroll(id="settings", classes="page"):
                    yield Label("设置 · 保存在用户配置目录", classes="heading")
                    for key, label in [
                        ("output_dir", "默认输出目录"),
                        ("download_dir", "下载目录"),
                        ("max_downloads", "最大并发下载数"),
                        ("download_limit", "下载限速（0 不限）"),
                        ("upload_limit", "上传限速（0 不限）"),
                        ("image_format", "默认图片格式（png / jpg / webp 等）"),
                        ("video_preset", "默认视频预设（balanced / high-quality / small / fast）"),
                        ("log_level", "日志等级（INFO / DEBUG / WARNING）"),
                    ]:
                        yield Label(label)
                        yield Input(str(self.config.get(key, "")), id=f"setting-{key}")
                    yield Select(
                        [("深色", "textual-dark"), ("浅色", "textual-light")],
                        value=self.config.get("theme", "textual-dark"),
                        allow_blank=False,
                        id="setting-theme",
                    )
                    yield Button("保存设置", id="settings-save", variant="primary")
                with VerticalScroll(id="about", classes="page"):
                    yield Label("Frees Tools v0.1.0 · 帮助", classes="heading")
                    yield Static(
                        "Your Ultimate Terminal Toolbox\n\n"
                        "Tab / Shift+Tab：切换焦点\n方向键：列表选择\nEnter：确认\n"
                        "Esc：首页 / 关闭弹窗\nF1：帮助\nCtrl+T：任务中心\nCtrl+Q：退出\n\n"
                        "文件浏览器：Enter 进入目录或选择文件；上级目录返回；多选列表可调整顺序。\n"
                        "图片多页输入需显式选择第一帧策略。宽或高留空时保持比例。\n"
                        "任务错误可在任务中心查看详情并重试。覆盖需显式允许。\n"
                        "视频依赖 FFmpeg / ffprobe，种子下载依赖 aria2c。\n"
                        "命令行 Frees-Tools doctor 提供环境诊断与安装建议。\n\n"
                        "项目：https://github.com/Frees-Ling/Frees-Tools\n许可证：MIT"
                    )
        yield Static("就绪", id="status", markup=False)
        yield Footer()

    def main_query(self, selector, expect_type=None):
        return self._main_screen.query_one(selector, expect_type)

    def on_mount(self) -> None:
        self._main_screen = self.screen
        self._closing = False
        self.main_query("#task-table", DataTable).add_columns(
            "ID", "模块", "状态", "进度", "输出 / 错误"
        )
        self.main_query("#torrent-table", DataTable).add_columns(
            "ID", "名称", "状态", "进度", "下载速度"
        )
        self.refresh_tasks()
        self._task_timer = self.set_interval(0.4, self.refresh_tasks)
        self._torrent_timer = self.set_interval(3, self.refresh_torrents)
        self.theme = self.config.get("theme", "textual-dark")
        self.resize_logo(self.size.width)

    def on_unmount(self) -> None:
        self._closing = True
        for timer in (getattr(self, "_task_timer", None), getattr(self, "_torrent_timer", None)):
            if timer is not None:
                timer.stop()

    def on_resize(self, event) -> None:
        if (
            self.is_mounted
            and hasattr(self, "_main_screen")
            and not getattr(self, "_closing", True)
        ):
            self.resize_logo(event.size.width)

    def resize_logo(self, width: int) -> None:
        self.main_query("#logo", Static).update(
            (LOGO if width >= 90 else "FREES TOOLS") + "\n v0.1.0 | Your Ultimate Terminal Toolbox"
        )
        self.main_query("#nav").styles.width = 28 if width >= 85 else 19

    @on(ListView.Selected, "#nav")
    def navigate(self, event: ListView.Selected) -> None:
        self.show_page(str(event.item.id).removeprefix("nav-"))

    def show_page(self, page: str) -> None:
        self.main_query("#pages", ContentSwitcher).current = page
        if page == "torrent":
            self.refresh_torrents()

    @work(thread=True)
    def cancel_task(self, task_id: str) -> None:
        try:
            self.manager.cancel(task_id)
        except Exception as error:
            self.call_from_thread(self.error, error)

    @work(thread=True)
    def retry_task(self, task_id: str) -> None:
        try:
            result = self.manager.retry(task_id)
            identity = result.get("id") if isinstance(result, dict) else result.id
            self.call_from_thread(setattr, self, "task_id", identity)
        except Exception as error:
            self.call_from_thread(self.error, error)

    def action_quit(self) -> None:
        active = [row for row in self.manager.list() if row["status"] in {"PENDING", "RUNNING"}]
        message = "退出会取消正在进行的图片 / 视频 / PDF 任务。" if active else "退出 Frees Tools？"
        message += "\naria2 下载在后台继续运行，重新打开可恢复管理。"
        self.push_screen(Confirm(message), lambda yes: self.shutdown_tasks() if yes else None)

    @work(thread=True)
    def shutdown_tasks(self) -> None:
        self.manager.close()
        self.call_from_thread(self.exit)

    def action_help(self) -> None:
        self.show_page("about")

    def action_tasks(self) -> None:
        self.show_page("tasks")

    def action_dashboard(self) -> None:
        self.show_page("dashboard")

    def value(self, field: str) -> str:
        return self.main_query(f"#{field}", Input).value.strip()

    def selected_value(self, field: str) -> str:
        return str(self.main_query(f"#{field}", Select).value)

    def checked(self, field: str) -> bool:
        return self.main_query(f"#{field}", Checkbox).value

    def status(self, message: str) -> None:
        self.main_query("#status", Static).update(message)

    def error(self, error: Exception) -> None:
        self.status(f"操作失败：{error}")
        self.push_screen(Detail("操作失败", {"error": str(error)}))

    def submit(self, module: str, fn: Callable, inputs: list[str], output: str) -> None:
        task = self.manager.submit(module, fn, inputs=inputs, output=output)
        self.task_id = task.id
        self.status(f"已提交任务 {task.id}，可在任务中心查看进度")
        self.show_page("tasks")
        self.refresh_tasks()

    def refresh_tasks(self) -> None:
        if getattr(self, "_closing", True):
            return
        tables = list(self._main_screen.query("#task-table"))
        if not tables or not tables[0].is_mounted:
            return
        rows = self.manager.list()
        table = self.main_query("#task-table", DataTable)
        values = [
            (
                str(row["id"]),
                (
                    str(row["id"])[:8],
                    str(row["module"]),
                    str(row["status"]),
                    f"{row.get('progress', 0):.0f}%",
                    str(row.get("error") or row.get("output") or ""),
                ),
            )
            for row in rows
        ]
        self.update_table(table, values, self.task_id)
        self.main_query("#dashboard-summary", Static).update(
            f"任务总数：{len(rows)}\n"
            + "  ".join(
                f"{state}: {sum(r['status'] == state for r in rows)}"
                for state in ("RUNNING", "COMPLETED", "FAILED", "CANCELLED")
            )
        )
        chosen = next((r for r in rows if r["id"] == self.task_id), None)
        if chosen:
            self.main_query("#task-progress", ProgressBar).update(
                progress=chosen.get("progress", 0)
            )
            self.main_query("#task-selected", Static).update(
                f"{chosen['id']} · {chosen['status']}\n{chosen.get('error') or chosen.get('output') or ''}"
                + "\n"
                + json.dumps(chosen.get("details", {}), ensure_ascii=False)
            )

    @staticmethod
    def update_table(
        table: DataTable, values: list[tuple[str, tuple]], selected: str | None
    ) -> None:
        """Update rows in place so polling never invalidates the current selection."""
        identities = {identity for identity, _ in values}
        existing = {str(key.value) for key in table.rows}
        for identity in existing - identities:
            table.remove_row(identity)
        columns = list(table.columns)
        for identity, cells in values:
            if identity not in existing:
                table.add_row(*cells, key=identity)
            else:
                for column, cell in zip(columns, cells):
                    table.update_cell(identity, column, cell, update_width=True)
        if selected in identities:
            table.move_cursor(row=table.get_row_index(selected))

    @staticmethod
    def current_row_id(table: DataTable) -> str | None:
        if 0 <= table.cursor_row < table.row_count:
            return str(table.ordered_rows[table.cursor_row].key.value)
        return None

    @on(DataTable.RowHighlighted, "#task-table")
    def task_highlight(self, event: DataTable.RowHighlighted) -> None:
        identity = str(event.row_key.value)
        if identity == self.current_row_id(event.data_table):
            self.task_id = identity

    @on(DataTable.RowHighlighted, "#torrent-table")
    def torrent_highlight(self, event: DataTable.RowHighlighted) -> None:
        identity = str(event.row_key.value)
        if identity == self.current_row_id(event.data_table):
            self.torrent_id = identity

    def browse(self, target: str, multiple: bool = False, directory: bool = False) -> None:
        def chosen(paths: list[str] | None) -> None:
            if not paths:
                return
            if target == "pdf":
                self.pdf_paths.extend(p for p in paths if p not in self.pdf_paths)
                self.refresh_pdf_list()
            else:
                if target == "image-source":
                    self.image_paths = paths
                self.main_query(f"#{target}", Input).value = paths[0]
                self.status(f"已选择 {len(paths)} 个项目")

        self.push_screen(FileBrowser(multiple=multiple, directory=directory), chosen)

    @work
    async def refresh_pdf_list(self) -> None:
        listing = self.main_query("#pdf-inputs", ListView)
        await listing.clear()
        await listing.extend(
            ListItem(Label(f"{i + 1}. [{Path(p).suffix.lstrip('.').upper()}] {p}", markup=False))
            for i, p in enumerate(self.pdf_paths)
        )

    @on(Input.Submitted, "#pdf-path")
    def add_pdf_path(self) -> None:
        path = self.value("pdf-path")
        if path:
            self.pdf_paths.append(str(Path(path).expanduser()))
            self.main_query("#pdf-path", Input).value = ""
            self.refresh_pdf_list()

    @on(Button.Pressed)
    def button_pressed(self, event: Button.Pressed) -> None:
        name = event.button.id or ""
        try:
            browsers = {
                "image-browse": ("image-source", True, False),
                "image-out-browse": ("image-output", False, True),
                "video-browse": ("video-source", False, False),
                "pdf-browse": ("pdf", True, False),
                "torrent-browse": ("torrent-source", False, False),
                "torrent-dir-browse": ("torrent-directory", False, True),
            }
            if name in browsers:
                self.browse(*browsers[name])
            elif name == "dashboard-tasks":
                self.action_tasks()
            elif name == "image-start":
                self.start_images()
            elif name == "video-start":
                self.start_video()
            elif name == "pdf-start":
                self.start_pdf()
            elif name in {"pdf-up", "pdf-down", "pdf-remove"}:
                listing = self.main_query("#pdf-inputs", ListView)
                index = listing.index
                if index is not None and index < len(self.pdf_paths):
                    other = index + (-1 if name == "pdf-up" else 1)
                    if name == "pdf-remove":
                        self.pdf_paths.pop(index)
                    elif 0 <= other < len(self.pdf_paths):
                        self.pdf_paths[index], self.pdf_paths[other] = (
                            self.pdf_paths[other],
                            self.pdf_paths[index],
                        )
                    self.refresh_pdf_list()
            elif name in {"image-info", "video-info", "pdf-info"}:
                module = name.split("-")[0]
                path = (
                    self.value(f"{module}-source")
                    if module != "pdf"
                    else (
                        self.pdf_paths[self.main_query("#pdf-inputs", ListView).index or 0]
                        if self.pdf_paths
                        else ""
                    )
                )
                self.media_info(module, path)
            elif name == "task-details":
                task = next((t for t in self.manager.list() if t["id"] == self.task_id), None)
                if task:
                    self.push_screen(Detail("任务详情", task))
            elif name == "task-cancel" and self.task_id:
                task_id = self.task_id
                self.push_screen(
                    Confirm("取消选中任务？临时输出会清理，原始文件保留。"),
                    lambda yes: self.cancel_task(task_id) if yes else None,
                )
            elif name == "task-retry" and self.task_id:
                task = next((t for t in self.manager.list() if t["id"] == self.task_id), None)
                if not task or task["status"] != "FAILED":
                    raise ValueError("只可重试失败任务")
                self.retry_task(self.task_id)
            elif name == "settings-save":
                self.save_settings()
            elif name == "torrent-remove" and self.torrent_id:
                delete = self.checked("torrent-delete-data")
                task_id = self.torrent_id

                def confirmed(yes: bool) -> None:
                    if yes and delete:
                        self.push_screen(
                            Confirm("最终确认：将永久删除该任务的已下载数据。"),
                            lambda final: (
                                self.torrent_action("remove", task_id, True) if final else None
                            ),
                        )
                    elif yes:
                        self.torrent_action("remove", task_id, False)

                self.push_screen(Confirm("删除选中的下载任务？"), confirmed)
            elif name.startswith("torrent-"):
                action = name.removeprefix("torrent-")
                if action == "refresh":
                    self.refresh_torrents()
                elif action in {"add", "details", "pause", "resume", "retry"}:
                    self.torrent_action(action, self.torrent_id)
        except Exception as error:
            self.error(error)

    def start_images(self) -> None:
        from frees_tools.services import images

        source = self.value("image-source")
        paths = (
            list(self.image_paths)
            if self.image_paths and source == self.image_paths[0]
            else [source]
        )
        if not source:
            raise ValueError("请选择输入图片")
        output = self.value("image-output") or self.config.get("output_dir") or None
        options = {
            "to": self.selected_value("image-format"),
            "quality": int(self.value("image-quality")),
            "width": int(self.value("image-width")) if self.value("image-width") else None,
            "height": int(self.value("image-height")) if self.value("image-height") else None,
            "scale": float(self.value("image-scale")) if self.value("image-scale") else None,
            "background": self.value("image-background"),
            "overwrite": self.checked("image-overwrite"),
            "first_frame": self.checked("image-first"),
        }

        targets = []
        for path in paths:
            target = (
                Path(output).expanduser()
                if output
                else Path(path).expanduser().with_suffix("." + options["to"])
            )
            if output and (len(paths) > 1 or target.is_dir() or not target.suffix):
                target = target / (Path(path).stem + "." + options["to"])
            targets.append(target.resolve())
        protected = {os.path.normcase(str(Path(path).expanduser().resolve())) for path in paths}
        destinations = [os.path.normcase(str(target)) for target in targets]
        if protected.intersection(destinations):
            raise ValueError(
                "输出路径指向已选输入文件，请选择其他输出目录或文件名；不会覆盖任何输入"
            )
        if len(set(destinations)) != len(destinations):
            raise ValueError("多个输入会生成相同输出文件名，请调整文件名或分开转换")

        def execute(progress, cancel):
            results = []
            for index, (path, target) in enumerate(zip(paths, targets)):
                result = images.convert(
                    path,
                    target,
                    **options,
                    progress=lambda value, *args, i=index: progress(
                        (i + float(value) / 100) / len(paths) * 100
                    ),
                    cancel=cancel,
                )
                results.append(result)
            return results

        self.submit("image", execute, paths, str(output or ""))

    def start_pdf(self) -> None:
        from frees_tools.services import pdf

        if not self.pdf_paths or not self.value("pdf-output"):
            raise ValueError("请添加输入文件并填写输出 PDF 路径")
        paths = list(self.pdf_paths)
        output = self.value("pdf-output")
        options = {
            "paper": self.selected_value("pdf-paper"),
            "fit": self.selected_value("pdf-fit"),
            "overwrite": self.checked("pdf-overwrite"),
        }
        self.submit(
            "pdf",
            lambda progress, cancel: pdf.combine(
                paths, output, **options, progress=progress, cancel=cancel
            ),
            paths,
            output,
        )

    def start_video(self) -> None:
        from frees_tools.services import video

        source, output = self.value("video-source"), self.value("video-output")
        if not source or not output:
            raise ValueError("请填写视频输入与输出文件路径")
        options = {
            "to": self.selected_value("video-format"),
            "preset": self.selected_value("video-preset"),
            "overwrite": self.checked("video-overwrite"),
            "codec": self.value("video-codec") or None,
            "quality": int(self.value("video-quality")) if self.value("video-quality") else None,
            "width": None,
            "height": None,
            "fps": float(self.value("video-fps")) if self.value("video-fps") else None,
            "audio_bitrate": self.value("video-bitrate"),
            "no_audio": not self.checked("video-audio"),
            "hardware": self.checked("video-hardware"),
        }
        resolution = self.value("video-resolution")
        if resolution:
            width, height = resolution.lower().split("x")
            options["width"], options["height"] = int(width), int(height)

        def execute(progress, cancel):
            if options["to"] in video.AUDIO:
                selected = {key: options[key] for key in ("to", "audio_bitrate", "overwrite")}
                return video.extract_audio(
                    source, output, **selected, progress=progress, cancel=cancel
                )
            return video.convert(source, output, **options, progress=progress, cancel=cancel)

        self.submit("video", execute, [source], output)

    @work(thread=True)
    def media_info(self, module: str, source: str) -> None:
        try:
            from importlib import import_module

            if module == "pdf" and Path(source).suffix.lower() != ".pdf":
                module = "images"
            if module == "image":
                module = "images"
            result = import_module(f"frees_tools.services.{module}").info(source)
            self.call_from_thread(self.push_screen, Detail("文件信息", result))
        except Exception as error:
            self.call_from_thread(self.error, error)

    def save_settings(self) -> None:
        from frees_tools.core.config import save_config

        config = dict(self.config)
        for key in (
            "output_dir",
            "download_dir",
            "max_downloads",
            "download_limit",
            "upload_limit",
            "image_format",
            "video_preset",
            "log_level",
        ):
            value = self.value(f"setting-{key}")
            config[key] = int(value) if key == "max_downloads" and value else value
        config["theme"] = self.selected_value("setting-theme")
        save_config(config)
        self.config = config
        self.theme = config["theme"]
        self.status("设置已保存")

    def get_torrent_service(self):
        if self.torrent_service is None:
            from frees_tools.services.torrent import TorrentService

            self.torrent_service = TorrentService()
        return self.torrent_service

    @work(thread=True, exclusive=True, group="torrent-refresh")
    def refresh_torrents(self) -> None:
        if getattr(self, "_closing", True) or not self.is_running:
            return
        page = self.call_from_thread(lambda: self.main_query("#pages", ContentSwitcher).current)
        if page not in {"torrent", "tasks"}:
            return
        if page == "tasks":
            from frees_tools.core.config import STATE_DIR

            if not (STATE_DIR / "torrent" / "runtime.json").exists():
                return
        try:
            rows = self.get_torrent_service().list()
            self.call_from_thread(self.render_torrents, rows)
        except Exception as error:
            self.call_from_thread(self.status, str(error))

    def render_torrents(self, rows: list[dict]) -> None:
        self.torrent_rows = rows
        table = self.main_query("#torrent-table", DataTable)
        values = []
        for row in rows:
            identity = str(row.get("id") or row.get("gid"))
            values.append(
                (
                    identity,
                    (
                        identity,
                        str(row.get("name", "")),
                        str(row.get("status", "")),
                        f"{row.get('progress', 0):.1f}%",
                        str(row.get("download_speed", row.get("downloadSpeed", ""))),
                    ),
                )
            )
        self.update_table(table, values, self.torrent_id)

    @work(thread=True, group="torrent-action")
    def torrent_action(self, action: str, task_id: str | None, delete_data: bool = False) -> None:
        try:
            service = self.get_torrent_service()
            if action == "add":
                source, directory, selection = self.call_from_thread(
                    lambda: (
                        self.value("torrent-source"),
                        self.value("torrent-directory"),
                        self.value("torrent-files"),
                    )
                )
                files = [int(x.strip()) for x in selection.split(",")] if selection else None
                result = service.add(source, directory, select_files=files)
            elif not task_id:
                raise ValueError("请先选择下载任务")
            elif action == "details":
                result = service.status(task_id)
            elif action == "remove":
                result = service.remove(task_id, delete_data=delete_data, confirm=delete_data)
            else:
                result = getattr(service, action)(task_id)
            self.call_from_thread(self.push_screen, Detail("下载操作结果 / 详情", result))
            self.call_from_thread(self.refresh_torrents)
        except Exception as error:
            self.call_from_thread(self.error, error)


def run() -> None:
    """Launch the interactive terminal application."""
    FreesToolsApp().run()
