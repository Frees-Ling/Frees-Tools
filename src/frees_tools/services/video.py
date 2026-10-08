"""FFmpeg conversion with structured progress and transactional outputs."""

from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
import queue
import re
import subprocess
import threading

from frees_tools.adapters.engines import find_engine
from frees_tools.core.errors import ToolError
from frees_tools.core.files import output_file

CONTAINERS = {
    "mp4": ("libx264", "aac"),
    "mov": ("libx264", "aac"),
    "mkv": ("libx264", "aac"),
    "webm": ("libvpx-vp9", "libopus"),
}
AUDIO = {"mp3": "libmp3lame", "wav": "pcm_s16le", "flac": "flac", "aac": "aac"}
PRESETS = {"high-quality": 18, "balanced": 23, "small": 30, "fast": 25}
ALLOWED = {
    "mp4": {"libx264", "libx265", "h264_videotoolbox", "h264_nvenc", "h264_qsv", "mpeg4"},
    "mov": {"libx264", "libx265", "h264_videotoolbox", "h264_nvenc", "h264_qsv", "prores_ks"},
    "mkv": {
        "libx264",
        "libx265",
        "libvpx-vp9",
        "libaom-av1",
        "h264_videotoolbox",
        "h264_nvenc",
        "h264_qsv",
    },
    "webm": {"libvpx-vp9", "libvpx", "libaom-av1"},
}


def info(path: str | Path) -> dict:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise ToolError(f"输入文件不存在: {source}")
    try:
        result = subprocess.run(
            [
                str(find_engine("ffprobe")),
                "-v",
                "error",
                "-show_format",
                "-show_streams",
                "-of",
                "json",
                str(source),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode:
            raise ToolError(f"无法读取媒体文件: {result.stderr[-2000:]}")
        data = json.loads(result.stdout)
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        raise ToolError(f"无法读取媒体信息: {exc}") from exc
    streams = data.get("streams", [])
    video = next((item for item in streams if item.get("codec_type") == "video"), {})
    return {
        "path": str(source),
        "duration": float(data.get("format", {}).get("duration", 0)),
        "size": source.stat().st_size,
        "width": video.get("width"),
        "height": video.get("height"),
        "video_codec": video.get("codec_name"),
        "streams": streams,
        "format": data.get("format", {}),
    }


@lru_cache(maxsize=8)
def _encoders(engine: str) -> frozenset[str]:
    result = subprocess.run(
        [engine, "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=15
    )
    return frozenset(
        match.group(1) for match in re.finditer(r"^\s*[VAS][A-Z.]{5}\s+(\S+)", result.stdout, re.M)
    )


@lru_cache(maxsize=16)
def _hardware_usable(engine: str, codec: str) -> bool:
    """Compiled-in encoders do not prove a working GPU or driver."""
    try:
        result = subprocess.run(
            [
                engine,
                "-v",
                "error",
                "-nostdin",
                "-f",
                "lavfi",
                "-i",
                "color=size=64x64:rate=1",
                "-frames:v",
                "1",
                "-c:v",
                codec,
                "-f",
                "null",
                "-",
            ],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def capabilities() -> dict:
    engine = str(find_engine("ffmpeg"))
    return {
        "encoders": sorted(_encoders(engine)),
        "containers": list(CONTAINERS),
        "audio": list(AUDIO),
    }


def parse_progress(values: dict, duration: float) -> dict:
    processed = float(values.get("out_time_us", values.get("out_time_ms", 0))) / 1_000_000
    speed_text = values.get("speed", "0x").rstrip("x")
    try:
        speed = float(speed_text)
    except ValueError:
        speed = 0.0
    return {
        "processed_seconds": processed,
        "progress": min(100.0, 100 * processed / duration) if duration else 0,
        "speed": speed,
        "eta": max(0, duration - processed) / speed if speed > 0 else None,
        "status": "COMPLETED" if values.get("progress") == "end" else "RUNNING",
    }


def _run(args: list[str], duration: float, progress=None, cancel=None) -> None:
    events: queue.Queue = queue.Queue()
    errors: list[str] = []
    process = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdin=subprocess.DEVNULL,
    )

    def read_stdout():
        for line in process.stdout:
            events.put(line.strip())
        events.put(None)

    def read_stderr():
        for line in process.stderr:
            errors.append(line)
            if len(errors) > 100:
                del errors[0]

    readers = [
        threading.Thread(target=read_stdout, daemon=True),
        threading.Thread(target=read_stderr, daemon=True),
    ]
    for reader in readers:
        reader.start()
    values = {}
    try:
        while True:
            if cancel is not None and cancel.is_set():
                raise ToolError("任务已取消")
            try:
                line = events.get(timeout=0.1)
            except queue.Empty:
                continue
            if line is None:
                break
            key, separator, value = line.partition("=")
            if separator:
                values[key] = value
            if key == "progress" and progress:
                progress(parse_progress(values, duration))
        code = process.wait()
        readers[1].join(timeout=2)
        if code:
            raise ToolError("FFmpeg 转换失败: " + "".join(errors)[-4000:])
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
        for reader in readers:
            reader.join(timeout=2)
        process.stdout.close()
        process.stderr.close()


def convert(
    source,
    output,
    to="mp4",
    preset="balanced",
    codec=None,
    quality=None,
    width=None,
    height=None,
    fps=None,
    audio_bitrate="192k",
    no_audio=False,
    hardware=False,
    overwrite=False,
    progress=None,
    cancel=None,
) -> dict:
    to = to.lower().lstrip(".")
    if to not in CONTAINERS:
        raise ToolError(f"不支持的视频格式: {to}")
    if preset not in PRESETS:
        raise ToolError(f"未知视频预设: {preset}")
    if any(value is not None and value <= 0 for value in (width, height, fps)):
        raise ToolError("宽度、高度和帧率必须大于零")
    if quality is not None and not 0 <= quality <= 51:
        raise ToolError("视频质量必须在 0 到 51 之间")
    if not re.fullmatch(r"\d+[kKmM]?", audio_bitrate):
        raise ToolError("音频码率应为 192k 等正整数格式")
    metadata = info(source)
    if not any(s.get("codec_type") == "video" for s in metadata["streams"]):
        raise ToolError("输入文件没有视频流；请使用音频提取")
    engine = str(find_engine("ffmpeg"))
    available = _encoders(engine)
    selected = codec or CONTAINERS[to][0]
    if hardware:
        candidates = ["h264_videotoolbox", "h264_nvenc", "h264_qsv"]
        selected = next(
            (
                item
                for item in candidates
                if item in available and item in ALLOWED[to] and _hardware_usable(engine, item)
            ),
            "",
        )
        if not selected:
            raise ToolError("没有与该容器兼容的硬件编码器；关闭硬件加速以使用软件编码。")
    if selected not in ALLOWED[to]:
        raise ToolError(f"编码器 {selected} 不兼容 {to} 容器")
    if selected not in available:
        raise ToolError(f"当前 FFmpeg 不提供编码器 {selected}；请更换编码器或安装完整版本。")
    args = [
        engine,
        "-hide_banner",
        "-nostdin",
        "-y",
        "-i",
        metadata["path"],
        "-map",
        "0:v:0",
        "-map",
        "0:a:0?",
        "-c:v",
        selected,
    ]
    if selected in {"libx264", "libx265"}:
        args += [
            "-crf",
            str(quality if quality is not None else PRESETS[preset]),
            "-preset",
            "ultrafast" if preset == "fast" else "medium",
        ]
    elif selected.startswith("libvpx"):
        args += ["-crf", str(quality if quality is not None else PRESETS[preset]), "-b:v", "0"]
    args += ["-pix_fmt", "yuv420p"]
    if width or height:
        args += [
            "-vf",
            f"scale={width or -2}:{height or -2}:force_original_aspect_ratio=decrease:force_divisible_by=2",
        ]
    if fps:
        args += ["-r", str(fps)]
    args += ["-an"] if no_audio else ["-c:a", CONTAINERS[to][1], "-b:a", audio_bitrate]
    if to in ("mp4", "mov"):
        args += ["-movflags", "+faststart"]
    destination = Path(output).expanduser().resolve()
    with output_file(destination, [Path(metadata["path"])], overwrite) as temporary:
        _run(
            args
            + [
                "-progress",
                "pipe:1",
                "-nostats",
                "-f",
                "matroska" if to == "mkv" else to,
                str(temporary),
            ],
            metadata["duration"],
            progress,
            cancel,
        )
        result = info(temporary)
        if progress:
            progress(
                {
                    "progress": 100.0,
                    "status": "COMPLETED",
                    "processed_seconds": metadata["duration"],
                    "eta": 0,
                }
            )
        if not any(s.get("codec_type") == "video" for s in result["streams"]):
            raise ToolError("输出校验失败：视频流缺失")
    result["path"] = str(destination)
    return result


def extract_audio(
    source, output, to="mp3", audio_bitrate="192k", overwrite=False, progress=None, cancel=None
) -> dict:
    to = to.lower().lstrip(".")
    if to not in AUDIO:
        raise ToolError(f"不支持的音频格式: {to}")
    if not re.fullmatch(r"\d+[kKmM]?", audio_bitrate):
        raise ToolError("音频码率应为 192k 等正整数格式")
    metadata = info(source)
    if not any(s.get("codec_type") == "audio" for s in metadata["streams"]):
        raise ToolError("输入文件没有音频流")
    engine = str(find_engine("ffmpeg"))
    if AUDIO[to] not in _encoders(engine):
        raise ToolError(f"当前 FFmpeg 不提供 {AUDIO[to]} 编码器")
    args = [
        engine,
        "-hide_banner",
        "-nostdin",
        "-y",
        "-i",
        metadata["path"],
        "-map",
        "0:a:0",
        "-vn",
        "-c:a",
        AUDIO[to],
    ]
    if to in ("mp3", "aac"):
        args += ["-b:a", audio_bitrate]
    destination = Path(output).expanduser().resolve()
    with output_file(destination, [Path(metadata["path"])], overwrite) as temporary:
        _run(
            args
            + [
                "-progress",
                "pipe:1",
                "-nostats",
                "-f",
                "adts" if to == "aac" else to,
                str(temporary),
            ],
            metadata["duration"],
            progress,
            cancel,
        )
        result = info(temporary)
        if progress:
            progress(
                {
                    "progress": 100.0,
                    "status": "COMPLETED",
                    "processed_seconds": metadata["duration"],
                    "eta": 0,
                }
            )
        if not any(s.get("codec_type") == "audio" for s in result["streams"]):
            raise ToolError("输出校验失败：音频流缺失")
    result["path"] = str(destination)
    return result
