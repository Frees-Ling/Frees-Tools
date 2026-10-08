"""Stable CLI; services are shared with the Textual application."""

import json
import sys
from pathlib import Path
from typing import Annotated
import typer
from rich.console import Console
from frees_tools import __version__
from frees_tools.core.errors import ToolError
from frees_tools.core.tasks import TaskManager

app = typer.Typer(no_args_is_help=False, help="Frees Tools — 图片、PDF、视频与 BitTorrent 工具箱")
image = typer.Typer(help="图片转换")
video = typer.Typer(help="视频与音频转换")
pdf = typer.Typer(help="PDF 合成")
torrent = typer.Typer(help="BitTorrent 下载管理")
config = typer.Typer(help="用户配置")
for name, group in [
    ("image", image),
    ("video", video),
    ("pdf", pdf),
    ("torrent", torrent),
    ("config", config),
]:
    app.add_typer(group, name=name)
JSON = False


def emit(value):
    if JSON:
        typer.echo(json.dumps(value, ensure_ascii=True, default=str))
    else:
        Console().print_json(json.dumps(value, ensure_ascii=False, default=str))


def execute(fn, module=None, inputs=None, output=""):
    try:
        if module:
            manager = TaskManager()
            try:
                task = manager.run(module, fn, inputs, output)
                if task.status != "COMPLETED":
                    raise ToolError(task.error or task.status)
                result = task.result
            finally:
                manager.close()
        else:
            result = fn()
        emit(result)
    except (ToolError, OSError, ValueError) as exc:
        if JSON:
            emit({"error": str(exc)})
        else:
            typer.echo(f"错误：{exc}", err=True)
        raise typer.Exit(1) from exc


@app.callback(invoke_without_command=True)
def root(
    ctx: typer.Context,
    version: Annotated[bool, typer.Option("--version", is_eager=True)] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
):
    global JSON
    JSON = json_output
    if version:
        typer.echo(__version__)
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        if JSON:
            emit({"name": "Frees Tools", "version": __version__})
        elif sys.stdin.isatty() and sys.stdout.isatty():
            from frees_tools.tui.app import FreesToolsApp

            FreesToolsApp().run()
        else:
            typer.echo(ctx.get_help())


@image.command("info")
def image_info(source: Path):
    from frees_tools.services import images

    execute(lambda: images.info(source))


@image.command("convert")
def image_convert(
    source: Path,
    to: str = "png",
    output: Path | None = None,
    quality: int = 90,
    width: int | None = None,
    height: int | None = None,
    scale: float | None = None,
    background: str = "#ffffff",
    overwrite: bool = False,
    first_frame: bool = False,
):
    from frees_tools.services import images

    execute(
        lambda p, c: images.convert(
            source,
            output=output,
            to=to,
            quality=quality,
            width=width,
            height=height,
            scale=scale,
            background=background,
            overwrite=overwrite,
            first_frame=first_frame,
            progress=p,
            cancel=c,
        ),
        "image",
        [str(source)],
        str(output or ""),
    )


@image.command("batch")
def image_batch(
    directory: Path,
    to: str = "webp",
    output_dir: Path = Path("converted"),
    pattern: str = "*",
    recursive: bool = False,
    overwrite: bool = False,
    quality: int = 90,
    first_frame: bool = False,
):
    from frees_tools.services import images

    execute(
        lambda p, c: images.batch(
            directory,
            to=to,
            output_dir=output_dir,
            pattern=pattern,
            recursive=recursive,
            overwrite=overwrite,
            quality=quality,
            first_frame=first_frame,
            progress=p,
            cancel=c,
        ),
        "image",
        [str(directory)],
        str(output_dir),
    )


@pdf.command("info")
def pdf_info(source: Path):
    from frees_tools.services import pdf as service

    execute(lambda: service.info(source))


def pdf_run(inputs, output, paper, fit, overwrite, mode):
    from frees_tools.services import pdf as service

    if mode == "merge" and any(p.suffix.lower() != ".pdf" for p in inputs):
        execute(lambda: (_ for _ in ()).throw(ToolError("merge 仅接受 PDF。")))
    if mode == "images" and any(p.suffix.lower() == ".pdf" for p in inputs):
        execute(lambda: (_ for _ in ()).throw(ToolError("from-images 仅接受图片。")))
    execute(
        lambda p, c: service.combine(
            inputs, output, paper=paper, fit=fit, overwrite=overwrite, progress=p, cancel=c
        ),
        "pdf",
        [str(p) for p in inputs],
        str(output),
    )


@pdf.command("merge")
def pdf_merge(
    inputs: list[Path],
    output: Annotated[Path, typer.Option()],
    paper: str = "auto",
    fit: str = "contain",
    overwrite: bool = False,
):
    pdf_run(inputs, output, paper, fit, overwrite, "merge")


@pdf.command("from-images")
def pdf_images(
    inputs: list[Path],
    output: Annotated[Path, typer.Option()],
    paper: str = "auto",
    fit: str = "contain",
    overwrite: bool = False,
):
    pdf_run(inputs, output, paper, fit, overwrite, "images")


@pdf.command("combine")
def pdf_combine(
    inputs: list[Path],
    output: Annotated[Path, typer.Option()],
    paper: str = "auto",
    fit: str = "contain",
    overwrite: bool = False,
):
    pdf_run(inputs, output, paper, fit, overwrite, "combine")


@video.command("info")
def video_info(source: Path):
    from frees_tools.services import video as service

    execute(lambda: service.info(source))


@video.command("convert")
def video_convert(
    source: Path,
    output: Annotated[Path, typer.Option()],
    to: str = "mp4",
    preset: str = "balanced",
    codec: str | None = None,
    quality: int | None = None,
    width: int | None = None,
    height: int | None = None,
    fps: float | None = None,
    audio_bitrate: str = "192k",
    no_audio: bool = False,
    hardware: bool = False,
    overwrite: bool = False,
):
    from frees_tools.services import video as service

    execute(
        lambda p, c: service.convert(
            source,
            output,
            to=to,
            preset=preset,
            codec=codec,
            quality=quality,
            width=width,
            height=height,
            fps=fps,
            audio_bitrate=audio_bitrate,
            no_audio=no_audio,
            hardware=hardware,
            overwrite=overwrite,
            progress=p,
            cancel=c,
        ),
        "video",
        [str(source)],
        str(output),
    )


@video.command("extract-audio")
def video_audio(
    source: Path,
    output: Annotated[Path, typer.Option()],
    to: str = "mp3",
    audio_bitrate: str = "192k",
    overwrite: bool = False,
):
    from frees_tools.services import video as service

    execute(
        lambda p, c: service.extract_audio(
            source,
            output,
            to=to,
            audio_bitrate=audio_bitrate,
            overwrite=overwrite,
            progress=p,
            cancel=c,
        ),
        "video",
        [str(source)],
        str(output),
    )


def ts():
    from frees_tools.services.torrent import TorrentService

    return TorrentService()


@torrent.command("add")
def torrent_add(
    source: str,
    directory: Annotated[Path | None, typer.Option("--dir")] = None,
    select_files: str | None = None,
):
    from frees_tools.core.config import load_config

    execute(
        lambda: ts().add(
            source, directory or Path(load_config()["download_dir"]), select_files=select_files
        )
    )


@torrent.command("list")
def torrent_list():
    execute(lambda: ts().list())


@torrent.command("status")
def torrent_status(task_id: str):
    execute(lambda: ts().status(task_id))


@torrent.command("pause")
def torrent_pause(task_id: str):
    execute(lambda: ts().pause(task_id))


@torrent.command("resume")
def torrent_resume(task_id: str):
    execute(lambda: ts().resume(task_id))


@torrent.command("retry")
def torrent_retry(task_id: str):
    execute(lambda: ts().retry(task_id))


@torrent.command("remove")
def torrent_remove(task_id: str, delete_data: bool = False, yes: bool = False):
    if delete_data and not yes:
        if not sys.stdin.isatty() or not typer.confirm(
            "确定永久删除此任务下载的文件？", default=False
        ):
            execute(
                lambda: (_ for _ in ()).throw(
                    ToolError("删除数据需要二次确认，自动化请同时提供 --delete-data --yes。")
                )
            )
    execute(lambda: ts().remove(task_id, delete_data=delete_data, confirm=yes or delete_data))


@torrent.command("shutdown")
def torrent_shutdown():
    execute(lambda: ts().shutdown())


@app.command("doctor")
def doctor():
    from frees_tools.adapters.engines import doctor as diagnose

    execute(diagnose)


@app.command("tasks")
def tasks():
    manager = TaskManager()
    try:
        emit(manager.list())
    finally:
        manager.close()


@config.command("show")
def config_show():
    from frees_tools.core.config import load_config

    emit(load_config())


@config.command("set")
def config_set(key: str, value: str):
    from frees_tools.core.config import load_config, save_config, DEFAULTS

    def update():
        if key not in DEFAULTS:
            raise ToolError("未知配置项。")
        data = load_config()
        try:
            parsed = json.loads(value)
        except ValueError:
            parsed = value
        data[key] = parsed
        return save_config(data)

    execute(update)


@app.command("self-test", hidden=True)
def self_test():
    """Exercise packaged Textual imports and responsive navigation without a TTY."""
    import asyncio
    from frees_tools.tui.app import FreesToolsApp
    from textual.widgets import ContentSwitcher

    async def check():
        application = FreesToolsApp()
        try:
            async with application.run_test(size=(110, 40)) as pilot:
                await pilot.press("ctrl+t")
                if application.query_one("#pages", ContentSwitcher).current != "tasks":
                    raise ToolError("TUI task navigation failed")
                await pilot.resize_terminal(60, 24)
                await pilot.press("escape")
                if application.query_one("#pages", ContentSwitcher).current != "dashboard":
                    raise ToolError("TUI responsive navigation failed")
            return {"tui": "passed", "sizes": ["110x40", "60x24"]}
        finally:
            application.manager.close()

    execute(lambda: asyncio.run(check()))


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    # Accept --json at every command depth without polluting machine output.
    if "--json" in sys.argv[1:]:
        sys.argv[:] = [sys.argv[0], "--json", *[v for v in sys.argv[1:] if v != "--json"]]
    app()


if __name__ == "__main__":
    main()
