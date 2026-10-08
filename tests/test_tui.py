"""Headless keyboard flows exercise the actual Textual screen and shared services."""

import asyncio

from PIL import Image
from textual.widgets import ContentSwitcher, Input, ListView, Static

from frees_tools.core.tasks import TaskManager
from frees_tools.tui.app import FileBrowser, FreesToolsApp


async def test_navigation_responsive_and_help(tmp_path, monkeypatch):
    monkeypatch.setattr("frees_tools.core.tasks.STATE_DIR", tmp_path)
    manager = TaskManager()
    app = FreesToolsApp(manager)
    async with app.run_test(size=(100, 40)) as pilot:
        assert "_____" in str(app.query_one("#logo", Static).render())
        await pilot.press("f1")
        assert app.query_one("#pages", ContentSwitcher).current == "about"
        await pilot.press("ctrl+t")
        assert app.query_one("#pages", ContentSwitcher).current == "tasks"
        await pilot.resize_terminal(60, 24)
        assert "FREES TOOLS" in str(app.query_one("#logo", Static).render())
        await pilot.press("escape")
        assert app.query_one("#pages", ContentSwitcher).current == "dashboard"
    manager.close()


async def test_file_browser_navigation_multiselect_order(tmp_path, monkeypatch):
    monkeypatch.setattr("frees_tools.core.tasks.STATE_DIR", tmp_path)
    folder = tmp_path / "中文 空格"
    folder.mkdir()
    (folder / "a.png").write_bytes(b"a")
    (folder / "b.png").write_bytes(b"b")
    manager = TaskManager()
    app = FreesToolsApp(manager)
    result = []
    async with app.run_test(size=(120, 50)) as pilot:
        browser = FileBrowser(tmp_path, multiple=True)
        app.push_screen(browser, result.append)
        await pilot.pause()
        browser.current = folder
        await browser.refresh_files()
        files = browser.query_one("#browser-files", ListView)
        files.focus()
        files.index = 0
        await pilot.press("enter", "down", "enter")
        assert browser.selected == [folder / "a.png", folder / "b.png"]
        selected = browser.query_one("#browser-selected", ListView)
        selected.index = 1
        await pilot.click("#browser-up")
        assert browser.selected == [folder / "b.png", folder / "a.png"]
        await pilot.click("#browser-use")
        assert result == [[str(folder / "b.png"), str(folder / "a.png")]]
    manager.close()


async def test_image_form_runs_real_conversion_in_shared_tasks(tmp_path, monkeypatch):
    monkeypatch.setattr("frees_tools.core.tasks.STATE_DIR", tmp_path)
    source = tmp_path / "原始 图片.png"
    target = tmp_path / "输出.webp"
    Image.new("RGBA", (20, 10), (10, 40, 80, 120)).save(source)
    manager = TaskManager()
    app = FreesToolsApp(manager)
    async with app.run_test(size=(120, 55)) as pilot:
        app.show_page("image")
        app.query_one("#image-source", Input).value = str(source)
        app.query_one("#image-output", Input).value = str(target)
        from textual.widgets import Select

        app.query_one("#image-format", Select).value = "webp"
        await pilot.pause()
        await pilot.click("#image-start")
        for _ in range(100):
            await asyncio.sleep(0.02)
            if manager.list() and manager.list()[0]["status"] in {"COMPLETED", "FAILED"}:
                break
        assert manager.list()[0]["status"] == "COMPLETED", manager.list()
        assert Image.open(target).format == "WEBP"
        assert source.exists()
        assert app.query_one("#pages", ContentSwitcher).current == "tasks"
    manager.close()


async def wait_for_task(manager, identity):
    for _ in range(200):
        row = next((item for item in manager.list() if item["id"] == identity), None)
        if row and row["status"] in {"COMPLETED", "FAILED", "CANCELLED"}:
            return row
        await asyncio.sleep(0.025)
    raise AssertionError("Task did not complete")


async def test_pdf_form_real_combine(tmp_path, monkeypatch):
    from pypdf import PdfReader, PdfWriter

    monkeypatch.setattr("frees_tools.core.tasks.STATE_DIR", tmp_path)
    first, photo, output = tmp_path / "一.pdf", tmp_path / "二.png", tmp_path / "混合.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=100)
    writer.write(first)
    Image.new("RGB", (30, 20), "blue").save(photo)
    manager = TaskManager()
    app = FreesToolsApp(manager)
    async with app.run_test(size=(120, 55)) as pilot:
        app.show_page("pdf")
        app.pdf_paths = [str(first), str(photo)]
        app.refresh_pdf_list()
        app.query_one("#pdf-output", Input).value = str(output)
        await pilot.pause()
        await pilot.click("#pdf-start")
        row = await wait_for_task(manager, app.task_id)
        assert row["status"] == "COMPLETED", row
        assert len(PdfReader(output).pages) == 2
    manager.close()


async def test_video_form_real_transcode(tmp_path, monkeypatch):
    import shutil
    import subprocess
    import pytest
    from frees_tools.services.video import info

    engine = shutil.which("ffmpeg")
    if not engine:
        pytest.skip("FFmpeg not installed")
    monkeypatch.setattr("frees_tools.core.tasks.STATE_DIR", tmp_path)
    source, output = tmp_path / "输入.mov", tmp_path / "输出.mp4"
    subprocess.run(
        [
            engine,
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=64x48:r=10:d=0.3",
            "-c:v",
            "mpeg4",
            str(source),
        ],
        check=True,
    )
    manager = TaskManager()
    app = FreesToolsApp(manager)
    async with app.run_test(size=(120, 55)) as pilot:
        app.show_page("video")
        app.query_one("#video-source", Input).value = str(source)
        app.query_one("#video-output", Input).value = str(output)
        app.query_one("#video-resolution", Input).value = "32x24"
        await pilot.pause()
        await pilot.click("#video-start")
        row = await wait_for_task(manager, app.task_id)
        assert row["status"] == "COMPLETED", row
        assert info(output)["width"] == 32
        assert row["details"]["processed_seconds"] > 0
    manager.close()


async def test_task_error_detail_retry_and_cancel_confirmation(tmp_path, monkeypatch):
    from frees_tools.tui.app import Confirm, Detail

    monkeypatch.setattr("frees_tools.core.tasks.STATE_DIR", tmp_path)
    manager = TaskManager()
    attempts = []

    def flaky(progress, cancel):
        attempts.append(True)
        if len(attempts) == 1:
            raise ValueError("真实失败详情")
        return {"ok": True}

    failed = manager.submit("test", flaky)
    assert (await wait_for_task(manager, failed.id))["status"] == "FAILED"
    app = FreesToolsApp(manager)
    async with app.run_test(size=(120, 55)) as pilot:
        app.show_page("tasks")
        app.task_id = failed.id
        await pilot.pause()
        await pilot.click("#task-details")
        assert isinstance(app.screen, Detail)
        assert app.screen.value["error"] == "真实失败详情"
        await pilot.press("escape")
        await pilot.click("#task-retry")
        await pilot.pause()
        retried = next(t for t in manager.list() if t["id"] != failed.id)
        assert retried["status"] == "COMPLETED"

        def running(progress, cancel):
            cancel.wait(10)

        active = manager.submit("test", running)
        app.refresh_tasks()
        await pilot.pause()
        app.task_id = active.id
        await pilot.click("#task-cancel")
        assert isinstance(app.screen, Confirm)
        await pilot.click("#yes")
        assert (await wait_for_task(manager, active.id))["status"] == "CANCELLED"
    manager.close()
