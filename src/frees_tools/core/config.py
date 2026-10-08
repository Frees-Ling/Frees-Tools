"""Validated per-user configuration, isolated from working directories."""

import json
import os
import re
import tempfile
import time
from contextlib import contextmanager
from threading import RLock
from pathlib import Path
from platformdirs import user_config_dir, user_state_dir
from .errors import ToolError

CONFIG_DIR = Path(os.environ.get("FREES_TOOLS_HOME", user_config_dir("Frees-Tools")))
STATE_DIR = Path(os.environ.get("FREES_TOOLS_HOME", user_state_dir("Frees-Tools")))
DEFAULTS = {
    "theme": "textual-dark",
    "language": "zh_CN",
    "output_dir": str(Path.home() / "Frees-Tools"),
    "download_dir": str(Path.home() / "Downloads"),
    "max_downloads": 3,
    "download_limit": "0",
    "upload_limit": "0",
    "completion_action": "keep",
    "image_format": "png",
    "video_preset": "balanced",
    "log_level": "INFO",
    "engines": {},
    "schema_version": 1,
}


_CONFIG_LOCK = RLock()


@contextmanager
def _config_lock():
    """Serialize readers/writers across threads and processes, including Windows."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with _CONFIG_LOCK, (CONFIG_DIR / ".config.lock").open("a+b") as stream:
        if os.name == "nt":
            import msvcrt

            if not stream.seek(0, os.SEEK_END):
                stream.write(b"0")
                stream.flush()
            stream.seek(0)
            deadline = time.monotonic() + 15
            while True:
                try:
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise ToolError("配置正被其他进程占用，请稍后重试")
                    time.sleep(0.05)
        else:
            import fcntl

            fcntl.flock(stream, fcntl.LOCK_EX)
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def _publish_config(temporary: Path, target: Path) -> None:
    # Windows antivirus/indexing can briefly hold a file without delete sharing.
    for attempt in range(20):
        try:
            temporary.replace(target)
            return
        except PermissionError:
            if attempt == 19:
                raise
            time.sleep(0.05)


def validate(data: dict) -> dict:
    result = DEFAULTS | data
    if result["schema_version"] != 1:
        raise ToolError("不支持的配置版本，请备份后重置配置。")
    if not isinstance(result["max_downloads"], int) or not 1 <= result["max_downloads"] <= 32:
        raise ToolError("下载并发数必须为 1–32。")
    for key in (
        "output_dir",
        "download_dir",
        "theme",
        "language",
        "image_format",
        "video_preset",
        "log_level",
        "download_limit",
        "upload_limit",
    ):
        if not isinstance(result[key], str):
            raise ToolError(f"配置项 {key} 必须是文本。")
    for key in ("download_limit", "upload_limit"):
        if not re.fullmatch(r"[0-9]+[KkMmGg]?", result[key]):
            raise ToolError(f"{key} 应为 0、1M 等速率。")
    if result["theme"] not in ("textual-dark", "textual-light"):
        raise ToolError("theme 仅支持 textual-dark 或 textual-light。")
    if result["language"] not in ("zh_CN", "en"):
        raise ToolError("language 仅支持 zh_CN 或 en。")
    if result["image_format"] not in ("png", "jpg", "jpeg", "webp", "bmp", "tif", "tiff", "gif"):
        raise ToolError("不支持的默认图片格式。")
    if result["video_preset"] not in ("balanced", "high-quality", "small", "fast"):
        raise ToolError("不支持的视频预设。")
    if result["log_level"] not in ("DEBUG", "INFO", "WARNING", "ERROR"):
        raise ToolError("不支持的日志等级。")
    if result.get("completion_action") != "keep":
        raise ToolError("首版完成行为仅支持 keep（保留记录）。")
    if not isinstance(result["engines"], dict):
        raise ToolError("engines 必须为路径映射。")
    if any(
        k not in ("ffmpeg", "ffprobe", "aria2c") or not isinstance(v, str)
        for k, v in result["engines"].items()
    ):
        raise ToolError("引擎路径配置必须为 ffmpeg/ffprobe/aria2c 的文本路径。")
    return result


def load_config() -> dict:
    path = CONFIG_DIR / "config.json"
    if not path.exists():
        return dict(DEFAULTS)
    with _config_lock():
        try:
            return validate(json.loads(path.read_text(encoding="utf-8")))
        except (ValueError, TypeError, ToolError):
            backup = path.with_suffix(".invalid.json")
            if not backup.exists():
                backup.write_bytes(path.read_bytes())
            return dict(DEFAULTS)


def save_config(data: dict) -> dict:
    result = validate(data)
    with _config_lock():
        fd, name = tempfile.mkstemp(prefix=".config-", suffix=".tmp", dir=CONFIG_DIR)
        temporary = Path(name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(result, stream, ensure_ascii=False, indent=2)
            _publish_config(temporary, CONFIG_DIR / "config.json")
        finally:
            temporary.unlink(missing_ok=True)
    return result
