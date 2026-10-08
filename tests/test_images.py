from threading import Event

import pytest
from PIL import Image

from frees_tools.core.errors import ToolError
from frees_tools.services import images


def test_formats_and_unicode_paths(tmp_path):
    source = tmp_path / "原始 图.png"
    Image.new("RGB", (24, 12), "red").save(source)
    original = source.read_bytes()
    for extension in ("png", "jpg", "jpeg", "webp", "bmp", "tiff", "gif"):
        destination = tmp_path / f"结果 图.{extension}"
        result = images.convert(source, destination, to=extension, width=12)
        assert result["width"] == 12
        assert result["height"] == 6
        assert result["size_bytes"] > 0
    assert source.read_bytes() == original


def test_alpha_background(tmp_path):
    source, destination = tmp_path / "alpha.png", tmp_path / "alpha.jpg"
    Image.new("RGBA", (10, 10), (0, 0, 0, 0)).save(source)
    images.convert(source, destination, to="jpg", background="#ff0000", quality=100)
    with Image.open(destination) as image:
        r, g, b = image.getpixel((5, 5))
        assert r > 250 and g < 5 and b < 5


def test_conflicts_and_cancel(tmp_path):
    source, output = tmp_path / "a.png", tmp_path / "out.png"
    Image.new("RGB", (10, 10)).save(source)
    with pytest.raises(ToolError):
        images.convert(source, source, overwrite=True)
    output.write_bytes(b"keep")
    with pytest.raises(ToolError):
        images.convert(source, output)
    event = Event()
    event.set()
    with pytest.raises(ToolError, match="取消"):
        images.convert(source, output, overwrite=True, cancel=event)
    assert output.read_bytes() == b"keep"


def test_multiframe_explicit_and_scale(tmp_path):
    source = tmp_path / "animated.gif"
    Image.new("RGB", (12, 6), "red").save(
        source, save_all=True, append_images=[Image.new("RGB", (12, 6), "blue")]
    )
    with pytest.raises(ToolError, match="first_frame"):
        images.convert(source, tmp_path / "out.png")
    result = images.convert(source, tmp_path / "out.png", first_frame=True, scale=50)
    assert (result["width"], result["height"], result["frames_discarded"]) == (6, 3, 1)


def test_batch_recursion_and_conflicts(tmp_path):
    source, target = tmp_path / "input", tmp_path / "output"
    (source / "子目录").mkdir(parents=True)
    Image.new("RGB", (2, 2)).save(source / "a.jpg")
    Image.new("RGB", (2, 2)).save(source / "子目录" / "b.png")
    result = images.batch(source, "webp", target, recursive=True)
    assert result["completed"] == 2 and result["failed"] == 0
    assert (target / "子目录" / "b.webp").exists()
    assert images.batch(source, "webp", target, recursive=True)["failed"] == 2


def test_exif_orientation(tmp_path):
    source = tmp_path / "portrait.jpg"
    exif = Image.Exif()
    exif[274] = 6
    Image.new("RGB", (20, 10)).save(source, exif=exif)
    result = images.convert(source, tmp_path / "portrait.png")
    assert (result["width"], result["height"]) == (10, 20)


def test_invalid_options_and_corruption(tmp_path):
    source = tmp_path / "bad.png"
    source.write_bytes(b"broken")
    with pytest.raises(ToolError):
        images.info(source)
    for options in (
        {"quality": 0},
        {"width": -1},
        {"scale": 0},
        {"scale": 50, "width": 10},
        {"background": "invalid"},
        {"to": "xyz"},
    ):
        with pytest.raises(ToolError):
            images.convert(source, **options)


def test_batch_name_collision_even_with_overwrite(tmp_path):
    source = tmp_path / "input"
    source.mkdir()
    for extension in ("png", "jpg"):
        Image.new("RGB", (2, 2)).save(source / f"same.{extension}")
    result = images.batch(source, "webp", tmp_path / "out", overwrite=True)
    assert result["completed"] == 1 and result["failed"] == 1
    assert "相同输出路径" in result["errors"][0]["error"]


def test_cancel_during_conversion_preserves_previous_output(tmp_path):
    source, output = tmp_path / "source.png", tmp_path / "out.jpg"
    Image.new("RGB", (10, 10)).save(source)
    output.write_bytes(b"previous")
    event = Event()
    with pytest.raises(ToolError, match="取消"):
        images.convert(
            source, output, to="jpg", overwrite=True, cancel=event, progress=lambda *_: event.set()
        )
    assert output.read_bytes() == b"previous"
    assert not list(tmp_path.glob(".frees-tools-*"))
