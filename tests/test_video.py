import shutil
import subprocess
import threading

import pytest

from frees_tools.core.errors import ToolError
from frees_tools.services import video


@pytest.fixture
def media(tmp_path):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("FFmpeg integration requires installed engine")
    path = tmp_path / "中文 视频.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=128x96:rate=10",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440",
            "-t",
            "1",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            str(path),
        ],
        check=True,
        timeout=30,
    )
    return path


def test_progress():
    result = video.parse_progress({"out_time_us": "2500000", "speed": "2.0x"}, 10)
    assert result["progress"] == 25
    assert result["eta"] == 3.75
    assert video.parse_progress({"speed": "N/A"}, 0)["eta"] is None


@pytest.mark.parametrize("format", ["mp4", "mov", "mkv", "webm"])
def test_real_video_conversion(media, tmp_path, format):
    output = tmp_path / f"输出 文件.{format}"
    events = []
    result = video.convert(
        media, output, to=format, preset="fast", width=64, progress=events.append
    )
    assert result["path"] == str(output)
    assert result["width"] == 64
    assert output.stat().st_size > 100
    assert events[-1]["status"] == "COMPLETED"
    assert media.is_file()


@pytest.mark.parametrize("format", ["mp3", "wav", "flac", "aac"])
def test_real_audio_extraction(media, tmp_path, format):
    result = video.extract_audio(media, tmp_path / f"音频.{format}", to=format)
    assert any(s["codec_type"] == "audio" for s in result["streams"])
    assert not any(s["codec_type"] == "video" for s in result["streams"])


def test_video_safety_and_cancel(media, tmp_path):
    with pytest.raises(ToolError, match="不兼容"):
        video.convert(media, tmp_path / "bad.webm", to="webm", codec="libx264")
    with pytest.raises(ToolError, match="源文件"):
        video.convert(media, media)
    output = tmp_path / "取消.mp4"
    output.write_bytes(b"existing data")
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(ToolError, match="取消"):
        video.convert(media, output, overwrite=True, cancel=cancel)
    assert output.read_bytes() == b"existing data"
    assert not list(tmp_path.glob(".frees-tools-*"))


def test_missing_input(tmp_path):
    with pytest.raises(ToolError, match="不存在"):
        video.info(tmp_path / "missing.mov")


def test_engine_missing_installation_guidance(monkeypatch):
    from frees_tools.adapters import engines

    monkeypatch.setattr(engines, "load_config", lambda: {"engines": {}})
    monkeypatch.setattr(engines.shutil, "which", lambda _: None)
    with pytest.raises(ToolError, match="找不到可用的 ffmpeg") as caught:
        engines.find_engine("ffmpeg")
    assert "安装" in str(caught.value)
    with pytest.raises(ToolError, match="未知"):
        engines.find_engine("untrusted-program")


def test_engine_configured_path(monkeypatch):
    from frees_tools.adapters import engines

    path = shutil.which("ffmpeg")
    if not path:
        pytest.skip("Requires local ffmpeg")
    monkeypatch.setattr(engines, "load_config", lambda: {"engines": {"ffmpeg": path}})
    monkeypatch.setattr(engines.shutil, "which", lambda _: None)
    assert engines.find_engine("ffmpeg") == __import__("pathlib").Path(path).resolve()
