"""Authenticated loopback aria2 daemon shared by all CLI and TUI clients.

The daemon deliberately survives clients. Explicit shutdown saves the session first.
"""

from __future__ import annotations

import base64
from contextlib import contextmanager
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import threading
import time
import tempfile
from urllib.error import URLError
from urllib.request import Request, ProxyHandler, build_opener

from frees_tools.adapters.engines import find_engine
from frees_tools.core import config
from frees_tools.core.errors import ToolError

_LOCAL_LOCK = threading.RLock()
_DAEMONS: dict[int, subprocess.Popen] = {}


def _atomic_json(path: Path, value: dict) -> None:
    temporary = path.with_name(path.name + "." + secrets.token_hex(6) + ".tmp")
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def _lock(path: Path):
    """OS releases lock even when a client crashes; no stale lock cleanup races."""
    with _LOCAL_LOCK, path.open("a+b") as stream:
        stream.seek(0)
        if os.name == "nt":
            import msvcrt

            if not path.stat().st_size:
                stream.write(b"0")
                stream.flush()
            stream.seek(0)
            deadline = time.monotonic() + 15
            while True:
                try:
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if time.monotonic() > deadline:
                        raise ToolError("下载服务被其他操作占用，请稍后重试")
                    time.sleep(0.1)
        else:
            import fcntl

            fcntl.flock(stream, fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == "nt":
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def _decode_torrent(data: bytes):
    index = 0

    def parse(depth=0):
        nonlocal index
        if depth > 100 or index >= len(data):
            raise ValueError("invalid torrent")
        marker = data[index : index + 1]
        if marker == b"i":
            end = data.index(b"e", index)
            value = int(data[index + 1 : end])
            index = end + 1
            return value
        if marker in (b"d", b"l"):
            index += 1
            value = {} if marker == b"d" else []
            while data[index : index + 1] != b"e":
                first = parse(depth + 1)
                if marker == b"d":
                    value[first] = parse(depth + 1)
                else:
                    value.append(first)
            index += 1
            return value
        colon = data.index(b":", index)
        length = int(data[index:colon])
        if length < 0 or colon + 1 + length > len(data):
            raise ValueError("invalid string")
        index = colon + 1 + length
        return data[colon + 1 : index]

    result = parse()
    if index != len(data) or not isinstance(result, dict):
        raise ValueError("invalid torrent")
    return result


def _validate_torrent(data: bytes) -> None:
    try:
        metadata = _decode_torrent(data)[b"info"]
        components = [metadata[b"name"]]
        for item in metadata.get(b"files", []):
            components.extend(item[b"path"])
        for raw in components:
            text = raw.decode("utf-8")
            if not text or text in (".", "..") or any(c in text for c in ("/", "\\", "\x00", ":")):
                raise ValueError("unsafe filename")
    except (KeyError, ValueError, TypeError, UnicodeError, IndexError, AttributeError) as exc:
        raise ToolError("种子损坏或包含不安全的文件路径") from exc


class TorrentService:
    def __init__(self, state_dir: Path | str | None = None):
        self.directory = Path(state_dir or config.STATE_DIR) / "torrent"
        self.directory.mkdir(parents=True, exist_ok=True)
        if os.name != "nt":
            self.directory.chmod(0o700)
        self.runtime_path = self.directory / "runtime.json"
        self.records_path = self.directory / "tasks.json"
        self.session_path = self.directory / "session.txt"
        self.lock_path = self.directory / "service.lock"
        self.runtime: dict = {}
        self._process: subprocess.Popen | None = None

    def _records(self) -> dict:
        try:
            return json.loads(self.records_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (ValueError, OSError) as exc:
            raise ToolError("下载记录不可读取，请保留文件后检查状态目录") from exc

    def _rpc(self, method: str, *params):
        payload = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": secrets.token_hex(4),
                "method": "aria2." + method,
                "params": ["token:" + self.runtime["token"], *params],
            }
        ).encode()
        request = Request(
            f"http://127.0.0.1:{self.runtime['port']}/jsonrpc",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            with build_opener(ProxyHandler({})).open(request, timeout=5) as response:
                result = json.load(response)
        except (OSError, URLError, ValueError) as exc:
            raise ToolError("无法连接本机 aria2 下载服务") from exc
        if "error" in result:
            message = result["error"].get("message", "未知错误")
            message = message.replace(self.runtime["token"], "[redacted]")
            raise ToolError(f"aria2: {message}")
        return result["result"]

    def _ensure(self):
        with _lock(self.lock_path):
            self._ensure_unlocked()

    def _ensure_unlocked(self):
        if self.runtime_path.exists():
            try:
                self.runtime = json.loads(self.runtime_path.read_text())
                self._rpc("getVersion")
                return
            except (ToolError, ValueError, KeyError):
                pid = self.runtime.get("pid")
                if pid:
                    from frees_tools.core.tasks import process_alive

                    if process_alive(pid):
                        raise ToolError(
                            "已有下载进程仍在运行但 RPC 不可达；请检查服务后重试，避免重复启动。"
                        )
        engine = find_engine("aria2c")
        cfg = config.load_config()
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        token = secrets.token_urlsafe(32)
        self.runtime = {"port": port, "token": token}
        self.session_path.touch(mode=0o600, exist_ok=True)
        engine_config = self.directory / "aria2.conf"
        lines = [
            "enable-rpc=true",
            "rpc-listen-all=false",
            f"rpc-listen-port={port}",
            f"rpc-secret={token}",
            "rpc-allow-origin-all=false",
            "disable-ipv6=true",
            "continue=true",
            "force-save=false",
            "save-session-interval=5",
            f"input-file={self.session_path}",
            f"save-session={self.session_path}",
            f"max-concurrent-downloads={cfg.get('max_downloads', 3)}",
            f"max-overall-download-limit={cfg.get('download_limit', '0')}",
            f"max-overall-upload-limit={cfg.get('upload_limit', '0')}",
            "seed-time=0",
            "bt-save-metadata=true",
            "bt-enable-lpd=false",
            "enable-dht=" + str(cfg.get("torrent_dht", True)).lower(),
            "enable-dht6=false",
            "console-log-level=error",
            "summary-interval=0",
            "download-result=hide",
        ]
        fd = os.open(engine_config, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write("\n".join(lines) + "\n")
        kwargs = {
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
        }
        if os.name == "nt":
            kwargs["creationflags"] = (
                subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
            )
        else:
            kwargs["start_new_session"] = True
        process = subprocess.Popen([str(engine), "--conf-path=" + str(engine_config)], **kwargs)
        self._process = process
        self.runtime["pid"] = process.pid
        _DAEMONS[process.pid] = process
        _atomic_json(self.runtime_path, self.runtime)
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if process.poll() is not None:
                self.runtime_path.unlink(missing_ok=True)
                raise ToolError("aria2 无法启动：检查状态目录、引擎和端口配置")
            try:
                self._rpc("getVersion")
                return
            except ToolError:
                time.sleep(0.1)
        process.terminate()
        process.wait(timeout=5)
        self.runtime_path.unlink(missing_ok=True)
        raise ToolError("aria2 启动超时")

    def add(self, source, directory, select_files=None) -> dict:
        destination = Path(directory).expanduser().resolve()
        destination.mkdir(parents=True, exist_ok=True)
        source = str(source)
        requested_directory = str(destination)
        if source.startswith("magnet:?"):
            destination = Path(tempfile.mkdtemp(prefix="Frees-Tools-", dir=destination))
        options = {
            "dir": str(destination),
            "allow-overwrite": "false",
            "auto-file-renaming": "false",
        }
        if select_files:
            indexes = (
                str(select_files)
                if isinstance(select_files, str)
                else ",".join(map(str, select_files))
            )
            import re

            if not re.fullmatch(r"[1-9]\d*(?:-[1-9]\d*)?(?:,[1-9]\d*(?:-[1-9]\d*)?)*", indexes):
                raise ToolError("文件选择应为 1,2 或 1-3 等索引")
            options["select-file"] = indexes
        payload = None
        delete_data_allowed = not any(destination.iterdir())
        if not source.startswith("magnet:?"):
            path = Path(source).expanduser().resolve()
            if not path.is_file() or path.suffix.lower() != ".torrent":
                raise ToolError("请输入 magnet 磁力链接或本地 .torrent 文件")
            if path.stat().st_size > 32 * 1024 * 1024:
                raise ToolError("种子文件过大（上限 32 MiB）")
            payload = path.read_bytes()
            _validate_torrent(payload)
            metadata = _decode_torrent(payload)[b"info"]
            name = metadata[b"name"].decode("utf-8")
            targets = [destination / name]
            if b"files" in metadata:
                targets = [
                    destination / name / Path(*[part.decode("utf-8") for part in item[b"path"]])
                    for item in metadata[b"files"]
                ]
            for target in targets:
                if not target.resolve().is_relative_to(destination):
                    raise ToolError("种子目标经过符号链接指向下载目录之外，已拒绝开始下载")
            delete_data_allowed = not any(
                target.exists()
                or target.is_symlink()
                or target.with_name(target.name + ".aria2").exists()
                or target.with_name(target.name + ".aria2").is_symlink()
                for target in targets
            )
            source = str(path)
        elif "xt=urn:btih:" not in source and "xt=urn:btmh:" not in source:
            raise ToolError("磁力链接缺少 BitTorrent 内容标识")
        with _lock(self.lock_path):
            self._ensure_unlocked()
            gid = (
                self._rpc("addTorrent", base64.b64encode(payload).decode(), [], options)
                if payload
                else self._rpc("addUri", [source], options)
            )
            records = self._records()
            records[gid] = {
                "id": gid,
                "source": source,
                "directory": str(destination),
                "requested_directory": requested_directory,
                "select_files": select_files,
                "created_at": time.time(),
                "started_at": None,
                "completed_at": None,
                "delete_data_allowed": delete_data_allowed,
            }
            _atomic_json(self.records_path, records)
            self._rpc("saveSession")
        return self.status(gid)

    def _normalize(self, data: dict, record: dict) -> dict:
        total = int(data.get("totalLength", 0))
        completed = int(data.get("completedLength", 0))
        speed = int(data.get("downloadSpeed", 0))
        destination = Path(record.get("directory", data.get("dir", "."))).resolve()
        files = data.get("files", [])
        if not data.get("bittorrent", {}).get("info") and all(
            str(item.get("path", "")).startswith("[METADATA]") for item in files
        ):
            files = []
        for item in files:
            if not item.get("path"):
                continue  # Magnet metadata does not have file paths yet.
            path = Path(item["path"]).resolve()
            if not path.is_relative_to(destination):
                try:
                    self._rpc("forcePause", data["gid"])
                except ToolError:
                    pass
                raise ToolError("下载元数据包含越界路径；已请求暂停任务")
        names = data.get("bittorrent", {}).get("info", {})
        status = {
            "active": "RUNNING",
            "waiting": "PENDING",
            "paused": "PAUSED",
            "complete": "COMPLETED",
            "error": "FAILED",
            "removed": "CANCELLED",
        }.get(data.get("status"), "PENDING")
        if status == "RUNNING" and not record.get("started_at"):
            record = {**record, "started_at": time.time()}
        if status in ("COMPLETED", "FAILED", "CANCELLED") and not record.get("completed_at"):
            record = {**record, "completed_at": time.time()}
        return {
            **record,
            "id": record.get("id", data["gid"]),
            "engine_id": data["gid"],
            "status": status,
            "name": names.get("name", Path(files[0]["path"]).name if files else data["gid"]),
            "total_size": total,
            "completed_size": completed,
            "progress": completed * 100 / total if total else 0,
            "download_speed": speed,
            "upload_speed": int(data.get("uploadSpeed", 0)),
            "eta": max(0, total - completed) / speed if speed else None,
            "peers": int(data.get("numSeeders", data.get("connections", 0))),
            "files": files,
            "directory": str(destination),
            "error": data.get("errorMessage", ""),
            "followed_by": data.get("followedBy", []),
        }

    def status(self, id: str) -> dict:
        self._ensure()
        with _lock(self.lock_path):
            records = self._records()
            if id not in records:
                raise ToolError("下载任务不存在")
            record = records[id]
            if record.get("status") in ("CANCELLED", "COMPLETED"):
                return record
            gid = record.get("engine_id", id)
            try:
                data = self._rpc("tellStatus", gid)
                # Magnet metadata is followed by the actual content task.
                if data.get("followedBy"):
                    data = self._rpc("tellStatus", data["followedBy"][0])
                result = self._normalize(data, record)
            except ToolError as exc:
                if record.get("status") in ("COMPLETED", "FAILED"):
                    return record
                raise ToolError(f"无法读取任务 {id}；可使用 retry 恢复。{exc}") from exc
            records[id] = result
            _atomic_json(self.records_path, records)
            return result

    def list(self) -> list[dict]:
        self._ensure()
        return [self.status(id) for id in self._records()]

    def _action(self, id: str, action: str) -> dict:
        current = self.status(id)
        self._rpc(action, current.get("engine_id", id))
        self._rpc("saveSession")
        return self.status(id)

    def pause(self, id: str) -> dict:
        return self._action(id, "forcePause")

    def resume(self, id: str) -> dict:
        return self._action(id, "unpause")

    def remove(self, id: str, delete_data=False, confirm=False) -> dict:
        if delete_data and not confirm:
            raise ToolError("删除实际下载数据必须明确二次确认")
        current = self.status(id)
        if delete_data and not current.get("delete_data_allowed", False):
            raise ToolError(
                "该任务目标在添加时已存在文件，无法安全确认数据归属；请保留任务数据并手动核对路径。"
            )
        gid = current.get("engine_id", id)
        if current["status"] in ("RUNNING", "PENDING", "PAUSED"):
            self._rpc("forceRemove", gid)
        elif current["status"] != "CANCELLED":
            try:
                self._rpc("removeDownloadResult", gid)
            except ToolError:
                # A saved completed record outlives aria2's in-memory results.
                if current["status"] not in ("COMPLETED", "FAILED"):
                    raise
        if delete_data:
            root = Path(current["directory"]).resolve()
            for item in current.get("files", []):
                path = Path(item["path"])
                if path.is_symlink() or not path.resolve().is_relative_to(root):
                    raise ToolError("拒绝删除下载目录之外的文件或符号链接")
            for item in current.get("files", []):
                path = Path(item["path"])
                if path.is_file():
                    path.unlink()
                control = path.with_name(path.name + ".aria2")
                if control.is_file() and not control.is_symlink():
                    control.unlink()
        current["status"] = "CANCELLED"
        with _lock(self.lock_path):
            records = self._records()
            records[id] = current
            _atomic_json(self.records_path, records)
            self._rpc("saveSession")
        return current

    def retry(self, id: str) -> dict:
        records = self._records()
        if id not in records:
            raise ToolError("下载任务不存在")
        record = records[id]
        if record.get("status") in ("RUNNING", "PENDING", "PAUSED"):
            raise ToolError("任务仍在队列中；请恢复或先移除任务")
        return self.add(
            record["source"],
            record.get("requested_directory", record["directory"]),
            record.get("select_files"),
        )

    def shutdown(self) -> dict:
        with _lock(self.lock_path):
            self._ensure_unlocked()
            self._rpc("saveSession")
            self._rpc("shutdown")
            # aria2 shutdown is asynchronous. Do not discard its identity until it exits.
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                try:
                    self._rpc("getVersion")
                except ToolError:
                    self.runtime_path.unlink(missing_ok=True)
                    if self._process is not None:
                        self._process.wait(timeout=3)
                        self._process = None
                    return {"status": "STOPPED", "session": str(self.session_path)}
                time.sleep(0.1)
            raise ToolError("aria2 停止超时；保留服务信息以便重新连接")
