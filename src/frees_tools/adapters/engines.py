"""Discover trusted local engines; never download executable code automatically."""

from __future__ import annotations

import importlib.metadata
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

from frees_tools.core.config import load_config
from frees_tools.core.errors import ToolError

ENGINES = ("ffmpeg", "ffprobe", "aria2c")


def installation_help() -> str:
    system = platform.system()
    if system == "Darwin":
        return "安装 Homebrew 后运行: brew install ffmpeg aria2"
    if system == "Windows":
        return "运行: winget install Gyan.FFmpeg 和 winget install aria2.aria2；重新打开终端。"
    return "使用发行版软件管理器安装 ffmpeg 和 aria2，例如: sudo apt install ffmpeg aria2"


def find_engine(name: str) -> Path:
    if name not in ENGINES:
        raise ToolError(f"未知外部引擎: {name}")
    executable = name + (".exe" if os.name == "nt" else "")
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    config = load_config()
    configured = config.get("engines", {}).get(name) or config.get(f"{name}_path")
    candidates = [root / "bin" / executable, root / "resources" / "bin" / executable]
    if configured:
        candidates.append(Path(configured).expanduser())
    found = shutil.which(executable)
    if found:
        candidates.append(Path(found))
    for candidate in candidates:
        if candidate.is_file() and (os.name == "nt" or os.access(candidate, os.X_OK)):
            try:
                result = subprocess.run(
                    [str(candidate), "-version" if name != "aria2c" else "--version"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if result.returncode == 0 and name.replace("c", "") in result.stdout.lower():
                    return candidate.resolve()
            except (OSError, subprocess.TimeoutExpired):
                continue
    raise ToolError(f"找不到可用的 {name}。{installation_help()}；也可在设置中指定引擎路径。")


def doctor() -> dict:
    from frees_tools.core.config import CONFIG_DIR

    directory = Path(CONFIG_DIR)
    config_error = None
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        config_error = str(exc)
    engines = {}
    for name in ENGINES:
        try:
            path = find_engine(name)
            result = subprocess.run(
                [str(path), "--version" if name == "aria2c" else "-version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            engines[name] = {
                "available": True,
                "path": str(path),
                "version": result.stdout.splitlines()[0],
            }
        except (ToolError, OSError, subprocess.TimeoutExpired) as exc:
            engines[name] = {"available": False, "error": str(exc)}
    dependencies = {}
    for name in ("textual", "typer", "Pillow", "pypdf", "platformdirs"):
        try:
            dependencies[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            dependencies[name] = None
    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "architecture": platform.machine(),
        "config_directory": str(directory),
        "config_writable": os.access(directory, os.W_OK),
        "config_error": config_error,
        "engines": engines,
        "dependencies": dependencies,
        "installation_help": installation_help(),
    }
