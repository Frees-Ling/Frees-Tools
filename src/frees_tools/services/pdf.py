"""PDF and image composition with ordered pages and atomic output."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any, Iterable

from PIL import Image, ImageOps
from pypdf import PageObject, PdfReader, PdfWriter, Transformation
from pypdf.errors import PyPdfError

from frees_tools.core.errors import ToolError
from frees_tools.core.files import output_file
from frees_tools.services.images import Progress, _check_cancel

PAPERS = {"a4": (595.2756, 841.8898), "a3": (841.8898, 1190.5512), "letter": (612, 792)}


def _reader(path: Path) -> PdfReader:
    try:
        reader = PdfReader(path)
        if reader.is_encrypted:
            if not reader.decrypt(""):
                reader.close()
                raise ToolError(f"PDF 已加密，需要先解除密码保护: {path.name}")
        if not len(reader.pages):
            reader.close()
            raise ToolError(f"PDF 没有页面: {path.name}")
        return reader
    except (OSError, ValueError, PyPdfError) as exc:
        raise ToolError(f"无法读取 PDF {path.name}: {exc}") from exc


def info(path: str | Path) -> dict:
    source = Path(path).expanduser().resolve()
    reader = _reader(source)
    try:
        return {
            "path": str(source),
            "pages": len(reader.pages),
            "encrypted": reader.is_encrypted,
            "size_bytes": source.stat().st_size,
            "page_sizes": [
                [float(page.mediabox.width), float(page.mediabox.height)] for page in reader.pages
            ],
        }
    finally:
        reader.close()


def _add_page(writer: PdfWriter, page: PageObject, paper: str, fit: str) -> None:
    if page.rotation:
        page = page.clone(writer)
        page.transfer_rotation_to_content()
    if paper == "auto":
        writer.add_page(page)
        return
    width, height = PAPERS[paper]
    source_w, source_h = float(page.mediabox.width), float(page.mediabox.height)
    if source_w <= 0 or source_h <= 0:
        raise ToolError("输入 PDF 页面尺寸无效")
    factor = (min if fit == "contain" else max)(width / source_w, height / source_h)
    x, y = (width - source_w * factor) / 2, (height - source_h * factor) / 2
    transform = (
        Transformation()
        .translate(-float(page.mediabox.left), -float(page.mediabox.bottom))
        .scale(factor)
        .translate(x, y)
    )
    target = writer.add_blank_page(width, height)
    target.merge_transformed_page(page, transform)


def combine(
    inputs: Iterable[str | Path],
    output: str | Path,
    paper: str = "auto",
    fit: str = "contain",
    overwrite: bool = False,
    progress: Progress | None = None,
    cancel: Any = None,
) -> dict:
    """Combine PDFs and all frames of images, in input order. Auto uses 96-DPI images."""
    sources = [Path(path).expanduser().resolve() for path in inputs]
    if not sources:
        raise ToolError("至少需要一个输入文件")
    paper, fit = paper.lower(), fit.lower()
    if paper not in {"auto", *PAPERS}:
        raise ToolError("纸张必须为 auto、A4、A3 或 Letter")
    if fit not in {"contain", "cover"}:
        raise ToolError("缩放模式必须为 contain（完整显示）或 cover（铺满裁切）")
    destination = Path(output).expanduser().resolve()
    writer = PdfWriter()
    readers = []
    try:
        with output_file(destination, sources, overwrite) as temporary:
            for index, source in enumerate(sources):
                _check_cancel(cancel)
                if source.suffix.lower() == ".pdf":
                    reader = _reader(source)
                    readers.append(reader)
                    for page in reader.pages:
                        _check_cancel(cancel)
                        _add_page(writer, page, paper, fit)
                else:
                    try:
                        with Image.open(source) as image:
                            for frame in range(getattr(image, "n_frames", 1)):
                                _check_cancel(cancel)
                                image.seek(frame)
                                oriented = ImageOps.exif_transpose(image)
                                rgba = oriented.convert("RGBA")
                                flattened = Image.new("RGB", rgba.size, "white")
                                flattened.paste(rgba, mask=rgba.getchannel("A"))
                                stream = BytesIO()
                                flattened.save(stream, format="PDF", resolution=96)
                                stream.seek(0)
                                # Only one decoded image is held at a time.
                                image_pdf = PdfReader(stream)
                                _add_page(writer, image_pdf.pages[0], paper, fit)
                    except (OSError, ValueError, Image.DecompressionBombError) as exc:
                        raise ToolError(f"无法将图片加入 PDF {source.name}: {exc}") from exc
                if progress:
                    progress((index + 1) * 90 / len(sources), f"已添加 {source.name}")
            _check_cancel(cancel)
            writer.write(temporary)
            with PdfReader(temporary) as check:
                if len(check.pages) != len(writer.pages):
                    raise ToolError("输出 PDF 页数验证失败")
            _check_cancel(cancel)
        result = info(destination)
        result.update(
            {
                "output": str(destination),
                "inputs": [str(p) for p in sources],
                "paper": paper,
                "fit": fit,
            }
        )
        if progress:
            progress(100, "PDF 合成完成")
        return result
    except (OSError, ValueError, PyPdfError) as exc:
        raise ToolError(f"PDF 合成失败: {exc}") from exc
    finally:
        writer.close()
        for reader in readers:
            reader.close()
