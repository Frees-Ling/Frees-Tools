import json
import os
import subprocess
import sys
from threading import Event
import pytest
from PIL import Image
from frees_tools.core.errors import ToolError
from frees_tools.core.files import output_file
from frees_tools.core.tasks import TaskManager
from frees_tools.core import config


def cli(*args, home):
    return subprocess.run(
        [sys.executable, "-m", "frees_tools.cli", *map(str, args)],
        text=True,
        capture_output=True,
        env=os.environ | {"FREES_TOOLS_HOME": str(home)},
        timeout=30,
    )


def test_cli_real_image_pdf_json(tmp_path):
    image = tmp_path / "中文 path.png"
    Image.new("RGBA", (10, 20), (0, 0, 0, 0)).save(image)
    output = tmp_path / "out.jpg"
    result = cli(
        "image",
        "convert",
        image,
        "--to",
        "jpg",
        "--output",
        output,
        "--json",
        home=tmp_path / "home",
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert json.loads(result.stdout)
    assert Image.open(output).format == "JPEG"
    result = cli(
        "--json",
        "pdf",
        "from-images",
        output,
        "--output",
        tmp_path / "out.pdf",
        home=tmp_path / "home",
    )
    assert result.returncode == 0, result.stdout
    result = cli(
        "image",
        "convert",
        image,
        "--to",
        "jpg",
        "--output",
        output,
        "--json",
        home=tmp_path / "home",
    )
    assert result.returncode == 1
    assert "error" in json.loads(result.stdout)
    result = cli("tasks", "--json", home=tmp_path / "home")
    statuses = [t["status"] for t in json.loads(result.stdout)]
    assert "FAILED" in statuses and "COMPLETED" in statuses


def test_noninteractive_help_version(tmp_path):
    assert "Usage" in cli(home=tmp_path).stdout
    assert cli("--version", home=tmp_path).stdout.strip() == "0.1.0"
    assert cli("image", "convert", "--help", home=tmp_path).returncode == 0
    assert cli("video", "convert", "--help", home=tmp_path).returncode == 0
    assert (
        cli("torrent", "remove", "fake", "--delete-data", "--json", home=tmp_path).returncode == 1
    )


def test_config_recovery(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path)
    config.save_config({"max_downloads": 5})
    assert config.load_config()["max_downloads"] == 5
    with pytest.raises(ToolError):
        config.save_config({"max_downloads": 0})
    (tmp_path / "config.json").write_text("broken")
    assert config.load_config()["max_downloads"] == 3
    assert (tmp_path / "config.invalid.json").read_text() == "broken"


def test_output_conflict_race(tmp_path):
    target = tmp_path / "out.txt"
    with pytest.raises(ToolError):
        with output_file(target) as temp:
            temp.write_text("new")
            target.write_text("other")
    assert target.read_text() == "other"
    assert not list(tmp_path.glob(".frees-tools-*"))


def test_tasks_cancel_retry(tmp_path, monkeypatch):
    import frees_tools.core.tasks as tasks

    monkeypatch.setattr(tasks, "STATE_DIR", tmp_path)
    manager = TaskManager()
    started = Event()

    def work(progress, cancel):
        started.set()
        cancel.wait(5)
        progress(20)

    task = manager.submit("image", work)
    assert started.wait(2)
    manager.cancel(task.id)
    manager.close()
    assert task.status == "CANCELLED"
    assert manager.list()[0]["status"] == "CANCELLED"


def test_task_failure_record(tmp_path, monkeypatch):
    import frees_tools.core.tasks as tasks

    monkeypatch.setattr(tasks, "STATE_DIR", tmp_path)
    manager = TaskManager()

    def fail(p, c):
        raise ToolError("fixture failure")

    task = manager.run("pdf", fail)
    assert task.status == "FAILED"
    assert task.error == "fixture failure"
    manager.close()


def test_shutdown_records_queued_cancellations(tmp_path, monkeypatch):
    import frees_tools.core.tasks as tasks

    monkeypatch.setattr(tasks, "STATE_DIR", tmp_path)
    manager = TaskManager()

    def work(progress, cancel):
        cancel.wait(5)

    jobs = [manager.submit("fixture", work) for _ in range(8)]
    manager.close()
    assert all(job.status == "CANCELLED" for job in jobs)
    assert all(row["status"] == "CANCELLED" for row in manager.list())


def test_late_cancel_after_successful_commit_is_completed(tmp_path, monkeypatch):
    import frees_tools.core.tasks as tasks

    monkeypatch.setattr(tasks, "STATE_DIR", tmp_path)
    manager = TaskManager()

    def committed(progress, cancel):
        (tmp_path / "complete.txt").write_text("valid output")
        cancel.set()
        progress(100)
        return {"output": str(tmp_path / "complete.txt")}

    job = manager.run("fixture", committed)
    assert job.status == "COMPLETED"
    assert job.result["output"].endswith("complete.txt")
    manager.close()
