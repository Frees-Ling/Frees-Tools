from threading import Event

import pytest
from PIL import Image
from pypdf import PdfReader, PdfWriter

from frees_tools.core.errors import ToolError
from frees_tools.services import pdf


def make_pdf(path, sizes=((100, 200),)):
    writer = PdfWriter()
    for width, height in sizes:
        writer.add_blank_page(width, height)
    writer.write(path)
    writer.close()


def test_merge_preserves_order(tmp_path):
    a, b, out = (tmp_path / name for name in ("一.pdf", "two.pdf", "结果.pdf"))
    make_pdf(a, ((100, 200), (110, 220)))
    make_pdf(b, ((300, 400),))
    result = pdf.combine([b, a], out)
    assert result["pages"] == 3
    assert pdf.info(out)["page_sizes"] == [[300, 400], [100, 200], [110, 220]]


def test_images_and_mixed_pdf(tmp_path):
    a, b, out = (tmp_path / name for name in ("透明 图片.png", "b.pdf", "out.pdf"))
    Image.new("RGBA", (96, 192), (0, 0, 0, 0)).save(a)
    make_pdf(b)
    assert pdf.combine([a, b, a], out)["pages"] == 3
    assert pdf.info(out)["page_sizes"][0] == [72, 144]
    with PdfReader(out) as reader:
        assert len(reader.pages[0].images) == 1


@pytest.mark.parametrize(
    "paper,expected",
    [("A4", (595.2756, 841.8898)), ("A3", (841.8898, 1190.5512)), ("Letter", (612, 792))],
)
@pytest.mark.parametrize("fit", ["contain", "cover"])
def test_paper_sizes(tmp_path, paper, expected, fit):
    source, output = tmp_path / "source.pdf", tmp_path / "out.pdf"
    make_pdf(source)
    pdf.combine([source], output, paper=paper, fit=fit)
    assert pdf.info(output)["page_sizes"][0] == pytest.approx(expected)


def test_all_tiff_pages(tmp_path):
    source, output = tmp_path / "pages.tiff", tmp_path / "out.pdf"
    Image.new("RGB", (10, 20)).save(
        source, save_all=True, append_images=[Image.new("RGB", (30, 40))]
    )
    assert pdf.combine([source], output)["pages"] == 2


def test_encrypted_corrupt_and_empty(tmp_path):
    encrypted, corrupt, empty = (tmp_path / name for name in ("locked.pdf", "bad.pdf", "empty.pdf"))
    writer = PdfWriter()
    writer.add_blank_page(100, 100)
    writer.encrypt("secret")
    writer.write(encrypted)
    writer.close()
    corrupt.write_bytes(b"not a PDF")
    make_pdf(empty, ())
    for path in (encrypted, corrupt, empty):
        with pytest.raises(ToolError):
            pdf.info(path)
        with pytest.raises(ToolError):
            pdf.combine([path], tmp_path / "out.pdf")
    assert not (tmp_path / "out.pdf").exists()


def test_output_protection_and_cancellation(tmp_path):
    source, output = tmp_path / "source.pdf", tmp_path / "out.pdf"
    make_pdf(source)
    original = source.read_bytes()
    with pytest.raises(ToolError):
        pdf.combine([source], source, overwrite=True)
    output.write_bytes(b"keep")
    with pytest.raises(ToolError):
        pdf.combine([source], output)
    event = Event()
    event.set()
    with pytest.raises(ToolError):
        pdf.combine([source], output, overwrite=True, cancel=event)
    assert output.read_bytes() == b"keep"
    assert source.read_bytes() == original


def test_invalid_arguments(tmp_path):
    with pytest.raises(ToolError):
        pdf.combine([], tmp_path / "out.pdf")
    with pytest.raises(ToolError):
        pdf.combine([tmp_path / "missing.pdf"], tmp_path / "out.pdf", paper="wrong")


def test_rotated_page_geometry(tmp_path):
    source, output = tmp_path / "rotated.pdf", tmp_path / "out.pdf"
    writer = PdfWriter()
    writer.add_blank_page(100, 200).rotate(90)
    writer.write(source)
    writer.close()
    pdf.combine([source], output)
    assert pdf.info(output)["page_sizes"] == [[200, 100]]


def test_cancel_during_combine_preserves_previous_output(tmp_path):
    source, output = tmp_path / "source.pdf", tmp_path / "out.pdf"
    make_pdf(source)
    output.write_bytes(b"previous")
    event = Event()
    with pytest.raises(ToolError, match="取消"):
        pdf.combine([source], output, overwrite=True, cancel=event, progress=lambda *_: event.set())
    assert output.read_bytes() == b"previous"
    assert not list(tmp_path.glob(".frees-tools-*"))
