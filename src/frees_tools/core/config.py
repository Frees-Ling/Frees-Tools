"""Validated per-user configuration, isolated from working directories."""

import json
import os
import re
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
    try:
        return validate(json.loads(path.read_text(encoding="utf-8")))
    except (ValueError, TypeError, ToolError):
        backup = path.with_suffix(".invalid.json")
        if not backup.exists():
            backup.write_bytes(path.read_bytes())
        return dict(DEFAULTS)


def save_config(data: dict) -> dict:
    result = validate(data)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    temporary = CONFIG_DIR / "config.tmp"
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(CONFIG_DIR / "config.json")
    return result
