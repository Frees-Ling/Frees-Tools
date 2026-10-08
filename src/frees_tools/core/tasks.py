"""Shared cancellable tasks and durable history for CLI and TUI."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
import json
import os
import sqlite3
from threading import Event, RLock
from uuid import uuid4
from .config import STATE_DIR
from .errors import ToolError
from .logging import configure


def now():
    return datetime.now(timezone.utc).isoformat()


def process_alive(pid):
    if not pid:
        return False
    if os.name == "nt":
        import ctypes

        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


@dataclass
class Task:
    id: str
    module: str
    inputs: list = field(default_factory=list)
    output: str = ""
    status: str = "PENDING"
    progress: float = 0
    created_at: str = field(default_factory=now)
    started_at: str | None = None
    completed_at: str | None = None
    error: str = ""
    result: object = None
    details: dict = field(default_factory=dict)
    owner_pid: int = field(default_factory=os.getpid)


class TaskManager:
    def __init__(self):
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        self.logger = configure()
        self.db = STATE_DIR / "tasks.sqlite3"
        self.lock = RLock()
        self.executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="frees")
        self.active = {}
        self.recipes = {}
        with sqlite3.connect(self.db) as db:
            db.execute("CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, payload TEXT)")

    def _save(self, task):
        with self.lock, sqlite3.connect(self.db) as db:
            db.execute(
                "INSERT OR REPLACE INTO tasks VALUES (?,?)",
                (task.id, json.dumps(asdict(task), ensure_ascii=False, default=str)),
            )

    def list(self):
        with self.lock, sqlite3.connect(self.db) as db:
            rows = [
                json.loads(row[0])
                for row in db.execute("SELECT payload FROM tasks ORDER BY rowid DESC")
            ]
        for row in rows:
            if (
                row["status"] in ("PENDING", "RUNNING")
                and row["id"] not in self.active
                and not process_alive(row.get("owner_pid"))
            ):
                row["status"] = "FAILED"
                row["error"] = "前次进程已结束，请重新提交此任务。"
        torrent_path = STATE_DIR / "torrent" / "tasks.json"
        if torrent_path.exists():
            try:
                records = json.loads(torrent_path.read_text(encoding="utf-8"))
                for record in records.values():
                    rows.append(
                        {
                            **record,
                            "module": "torrent",
                            "inputs": [record.get("source", "")],
                            "output": record.get("directory", ""),
                            "details": record,
                        }
                    )
            except (OSError, ValueError):
                self.logger.warning("torrent.history.unreadable")
        return rows

    def submit(self, module, fn, inputs=None, output=""):
        task = Task(uuid4().hex[:12], module, list(inputs or []), str(output))
        self.recipes[task.id] = (module, fn, inputs, output)
        event = Event()
        self.active[task.id] = (task, event)
        self._save(task)
        self.executor.submit(self._run, task, fn, event)
        return task

    def run(self, module, fn, inputs=None, output=""):
        task = Task(uuid4().hex[:12], module, list(inputs or []), str(output))
        event = Event()
        self.active[task.id] = (task, event)
        return self._run(task, fn, event)

    def _run(self, task, fn, event):
        task.status, task.started_at = "RUNNING", now()
        self._save(task)

        committed = False

        def update(value=None, *args, **details):
            nonlocal committed
            completion = value.get("progress", 0) if isinstance(value, dict) else value
            if event.is_set() and (not isinstance(completion, (int, float)) or completion < 100):
                raise ToolError("任务已取消")
            if isinstance(completion, (int, float)) and completion >= 100:
                committed = True
            if isinstance(value, dict) and value.get("status") == "COMPLETED":
                committed = True
            if isinstance(value, dict):
                task.details = dict(value)
                value = value.get("progress", value.get("percent", task.progress))
            if args:
                task.details["message"] = str(args[0])
            if isinstance(value, (int, float)):
                task.progress = max(0, min(100, float(value)))
            self._save(task)

        try:
            if event.is_set():
                raise ToolError("任务已取消")
            task.result = fn(update, event)
            if isinstance(task.result, dict) and task.result.get("failed", 0):
                raise ToolError(json.dumps(task.result, ensure_ascii=False))
            task.status = "COMPLETED" if committed or not event.is_set() else "CANCELLED"
            if task.status == "COMPLETED":
                task.progress = 100
        except BaseException as exc:
            if isinstance(exc, KeyboardInterrupt):
                event.set()
            task.status = "CANCELLED" if event.is_set() else "FAILED"
            task.error = str(exc)
        finally:
            task.completed_at = now()
            self.logger.info("task.%s.%s", task.module, task.status.lower())
            self._save(task)
            self.active.pop(task.id, None)
        return task

    def cancel(self, task_id):
        if task_id not in self.active:
            from frees_tools.services.torrent import TorrentService

            service = TorrentService()
            if service.records_path.exists() and task_id in service._records():
                return service.remove(task_id)
            raise ToolError("任务当前未运行。")
        self.active[task_id][1].set()

    def retry(self, task_id):
        if task_id not in self.recipes:
            from frees_tools.services.torrent import TorrentService

            service = TorrentService()
            if service.records_path.exists() and task_id in service._records():
                return service.retry(task_id)
            raise ToolError("重启后请在对应工具页重新提交任务。")
        return self.submit(*self.recipes[task_id])

    def close(self):
        for _, event in list(self.active.values()):
            event.set()
        self.executor.shutdown(wait=True, cancel_futures=False)
