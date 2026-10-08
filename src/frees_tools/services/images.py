"""Image inspection and conversion shared by CLI and TUI."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from PIL import Image, ImageColor, ImageOps, UnidentifiedImageError

from frees_tools.core.errors import ToolError
from frees_tools.core.files import output_file

FORMATS = {
    "png": "PNG",
    "jpg": "JPEG",
    "jpeg": "JPEG",
    "webp": "WEBP",
    "bmp": "BMP",
    "tif": "TIFF",
    "tiff": "TIFF",
    "gif": "GIF",
}
Progress = Callable[[float, str], None]


def _check_cancel(cancel: Any) -> None:
    if cancel is not None and (cancel.is_set() if hasattr(cancel, "is_set") else cancel()):
        raise ToolError("操作已取消")


def info(path: str | Path) -> dict:
    source = Path(path).expanduser().resolve()
    try:
        with Image.open(source) as image:
            return {
                "path": str(source),
                "format": image.format,
                "width": image.width,
                "height": image.height,
                "mode": image.mode,
                "frames": getattr(image, "n_frames", 1),
                "size_bytes": source.stat().st_size,
                "animated": bool(getattr(image, "is_animated", False)),
            }
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
        raise ToolError(f"无法读取图片 {source.name}: {exc}") from exc


def convert(
    source: str | Path,
    output: str | Path | None = None,
    to: str = "png",
    quality: int = 90,
    width: int | None = None,
    height: int | None = None,
    scale: float | None = None,
    background: str = "#ffffff",
    overwrite: bool = False,
    first_frame: bool = False,
    progress: Progress | None = None,
    cancel: Any = None,
) -> dict:
    """Convert one image. Width/height bound its aspect ratio; scale is a percentage.

    Multi-frame inputs require an explicit first_frame opt-in, including GIF to GIF.
    This avoids accidentally dropping animation or TIFF pages.
    """
    source = Path(source).expanduser().resolve()
    to = to.lower().lstrip(".")
    if to not in FORMATS:
        raise ToolError(f"不支持的输出格式: {to}；可选: {', '.join(FORMATS)}")
    if not 1 <= quality <= 100:
        raise ToolError("图片质量必须在 1 到 100 之间")
    if any(value is not None and value <= 0 for value in (width, height, scale)):
        raise ToolError("尺寸和缩放百分比必须大于 0")
    if scale is not None and (width is not None or height is not None):
        raise ToolError("缩放百分比不能与宽度或高度同时使用")
    try:
        color = ImageColor.getcolor(background, "RGB")
    except ValueError as exc:
        raise ToolError(f"无效的背景颜色: {background}") from exc
    destination = Path(output).expanduser() if output else source.with_suffix(f".{to}")
    _check_cancel(cancel)
    original = info(source)
    if original["frames"] > 1 and not first_frame:
        raise ToolError("输入包含多个帧或页面；请明确选择 first_frame / --first-frame 仅转换第一帧")
    try:
        with Image.open(source) as opened:
            image = ImageOps.exif_transpose(opened)
            image.load()
            if scale is not None:
                size = (
                    max(1, round(image.width * scale / 100)),
                    max(1, round(image.height * scale / 100)),
                )
            elif width is not None or height is not None:
                factor = min(
                    width / image.width if width else float("inf"),
                    height / image.height if height else float("inf"),
                )
                size = (max(1, round(image.width * factor)), max(1, round(image.height * factor)))
            else:
                size = image.size
            if size != image.size:
                image = image.resize(size, Image.Resampling.LANCZOS)
            if FORMATS[to] in {"JPEG", "BMP"}:
                if "A" in image.getbands() or "transparency" in image.info:
                    rgba = image.convert("RGBA")
                    image = Image.new("RGB", rgba.size, color)
                    image.paste(rgba, mask=rgba.getchannel("A"))
                else:
                    image = image.convert("RGB")
            elif FORMATS[to] == "GIF":
                image = image.convert("RGBA")
            elif image.mode == "CMYK" and FORMATS[to] in {"PNG", "WEBP"}:
                image = image.convert("RGB")
            if progress:
                progress(25, f"正在转换 {source.name}")
            with output_file(destination, [source], overwrite) as temporary:
                image.save(temporary, format=FORMATS[to], quality=quality)
                with Image.open(temporary) as check:
                    check.verify()
                _check_cancel(cancel)
        result = info(destination)
        result.update(
            {
                "input": str(source),
                "output": result["path"],
                "original_size_bytes": original["size_bytes"],
                "frames_discarded": original["frames"] - 1,
            }
        )
        if progress:
            progress(100, f"已保存 {destination.name}")
        return result
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        raise ToolError(f"图片转换失败: {exc}") from exc


def batch(
    directory: str | Path,
    to: str,
    output_dir: str | Path,
    pattern: str = "*",
    recursive: bool = False,
    overwrite: bool = False,
    **options: Any,
) -> dict:
    """Convert a stable sorted snapshot, preserving recursive relative directories.

    Per-file errors are returned explicitly, so partial success cannot masquerade as success.
    """
    root = Path(directory).expanduser().resolve()
    target = Path(output_dir).expanduser().resolve()
    if not root.is_dir():
        raise ToolError(f"图片输入目录不存在: {root}")
    if to.lower().lstrip(".") not in FORMATS:
        raise ToolError(f"不支持的输出格式: {to}")
    if Path(pattern).is_absolute() or ".." in Path(pattern).parts:
        raise ToolError("匹配规则必须是目录内部的相对规则")
    extensions = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".gif"}
    paths = sorted(
        path
        for path in (root.rglob(pattern) if recursive else root.glob(pattern))
        if path.is_file()
        and path.suffix.lower() in extensions
        and not (target != root and target in path.resolve().parents)
    )
    if not paths:
        raise ToolError("没有找到匹配的图片文件")
    progress = options.pop("progress", None)
    cancel = options.get("cancel")
    results, errors = [], []
    reserved: set[Path] = set()
    for index, path in enumerate(paths):
        _check_cancel(cancel)
        relative = path.relative_to(root).with_suffix(f".{to.lower().lstrip('.')}")
        destination = target / relative
        try:
            if destination in reserved:
                raise ToolError(f"多个输入映射到相同输出路径: {destination}")
            reserved.add(destination)
            results.append(convert(path, destination, to=to, overwrite=overwrite, **options))
        except ToolError as exc:
            _check_cancel(cancel)
            errors.append({"input": str(path), "error": str(exc)})
        if progress:
            progress((index + 1) * 100 / len(paths), f"{index + 1}/{len(paths)}: {path.name}")
    return {
        "total": len(paths),
        "completed": len(results),
        "failed": len(errors),
        "results": results,
        "errors": errors,
        "output_dir": str(target),
    }
