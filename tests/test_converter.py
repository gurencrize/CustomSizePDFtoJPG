from pathlib import Path

import pymupdf
import pytest
from PIL import Image

from pdf2jpg import (
    ConversionError,
    ConvertOptions,
    convert_pdf,
    parse_pages,
    parse_size,
)
from pdf2jpg.cli import main


@pytest.fixture
def sample_pdf(tmp_path: Path) -> Path:
    """A4縦 3ページ (595x842pt) のテスト用 PDF."""
    path = tmp_path / "sample.pdf"
    document = pymupdf.open()
    for index in range(3):
        page = document.new_page(width=595, height=842)
        page.insert_text((72, 144), f"page {index + 1}", fontsize=48)
    document.save(path)
    document.close()
    return path


def test_parse_size_variants():
    assert parse_size("1920x1080") == (1920, 1080)
    assert parse_size("1080x") == (1080, None)
    assert parse_size("x720") == (None, 720)
    assert parse_size(" 800×600 ") == (800, 600)


@pytest.mark.parametrize("spec", ["", "abc", "x", "0x100", "100*100"])
def test_parse_size_rejects_bad_input(spec):
    with pytest.raises(ValueError):
        parse_size(spec)


def test_parse_pages():
    assert parse_pages("1,3-5", 10) == [0, 2, 3, 4]
    assert parse_pages("8-", 10) == [7, 8, 9]
    assert parse_pages("-2", 10) == [0, 1]
    assert parse_pages("", 3) == [0, 1, 2]
    assert parse_pages("2,2,2", 3) == [1]  # 重複は除去される
    assert parse_pages("2-99", 3) == [1, 2]  # 総ページ数で打ち切り


@pytest.mark.parametrize("spec", ["0", "5-1", "a-b"])
def test_parse_pages_rejects_bad_input(spec):
    with pytest.raises(ValueError):
        parse_pages(spec, 10)


def test_convert_all_pages_with_dpi(sample_pdf, tmp_path):
    outputs = convert_pdf(sample_pdf, tmp_path / "out", ConvertOptions(dpi=72))
    assert [p.name for p in outputs] == [
        "sample_p001.jpg",
        "sample_p002.jpg",
        "sample_p003.jpg",
    ]
    with Image.open(outputs[0]) as image:
        assert image.size == (595, 842)
        assert image.format == "JPEG"


def test_exact_size_is_respected(sample_pdf, tmp_path):
    outputs = convert_pdf(
        sample_pdf, tmp_path, ConvertOptions(width=1920, height=1080, fit="contain")
    )
    for path in outputs:
        with Image.open(path) as image:
            assert image.size == (1920, 1080)


def test_contain_pads_with_background_color(sample_pdf, tmp_path):
    outputs = convert_pdf(
        sample_pdf,
        tmp_path,
        ConvertOptions(width=1000, height=1000, fit="contain", background="#ff0000",
                       pages=[0], quality=100),
    )
    with Image.open(outputs[0]) as image:
        red, green, blue = image.getpixel((5, 500))
        assert red > 200 and green < 60 and blue < 60


def test_cover_crops_instead_of_padding(sample_pdf, tmp_path):
    outputs = convert_pdf(
        sample_pdf,
        tmp_path,
        ConvertOptions(width=600, height=600, fit="cover", background="#ff0000",
                       pages=[0], quality=100),
    )
    with Image.open(outputs[0]) as image:
        assert image.size == (600, 600)
        red, green, blue = image.getpixel((5, 300))
        assert red > 200 and green > 200 and blue > 200  # 余白ではなくページの白


def test_width_only_keeps_aspect_ratio(sample_pdf, tmp_path):
    outputs = convert_pdf(sample_pdf, tmp_path, ConvertOptions(width=595, pages=[0]))
    with Image.open(outputs[0]) as image:
        assert image.size == (595, 842)


def test_height_only_keeps_aspect_ratio(sample_pdf, tmp_path):
    outputs = convert_pdf(sample_pdf, tmp_path, ConvertOptions(height=842, pages=[0]))
    with Image.open(outputs[0]) as image:
        assert image.size == (595, 842)


def test_scale_option(sample_pdf, tmp_path):
    outputs = convert_pdf(sample_pdf, tmp_path, ConvertOptions(scale=2.0, pages=[0]))
    with Image.open(outputs[0]) as image:
        assert image.size == (1190, 1684)


def test_grayscale_output(sample_pdf, tmp_path):
    outputs = convert_pdf(
        sample_pdf, tmp_path, ConvertOptions(width=200, grayscale=True, pages=[0])
    )
    with Image.open(outputs[0]) as image:
        assert image.mode == "L"


def test_quality_affects_file_size(sample_pdf, tmp_path):
    low = convert_pdf(
        sample_pdf, tmp_path / "low", ConvertOptions(width=1200, quality=20, pages=[0])
    )[0]
    high = convert_pdf(
        sample_pdf, tmp_path / "high", ConvertOptions(width=1200, quality=95, pages=[0])
    )[0]
    assert low.stat().st_size < high.stat().st_size


def test_selected_pages_only(sample_pdf, tmp_path):
    outputs = convert_pdf(sample_pdf, tmp_path, ConvertOptions(width=100, pages=[2]))
    assert [p.name for p in outputs] == ["sample_p003.jpg"]


def test_missing_file_raises(tmp_path):
    with pytest.raises(ConversionError):
        convert_pdf(tmp_path / "nope.pdf", tmp_path)


def test_out_of_range_page_raises(sample_pdf, tmp_path):
    with pytest.raises(ConversionError):
        convert_pdf(sample_pdf, tmp_path, ConvertOptions(pages=[99]))


def test_encrypted_pdf_raises(tmp_path):
    path = tmp_path / "locked.pdf"
    document = pymupdf.open()
    document.new_page()
    document.save(path, encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="secret")
    document.close()
    with pytest.raises(ConversionError):
        convert_pdf(path, tmp_path / "out")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"width": 0},
        {"height": -10},
        {"dpi": 0},
        {"scale": 0},
        {"fit": "unknown"},
        {"quality": 0},
        {"quality": 101},
    ],
)
def test_invalid_options_rejected(kwargs):
    with pytest.raises(ValueError):
        ConvertOptions(**kwargs)


def test_cli_end_to_end(sample_pdf, tmp_path, capsys):
    out_dir = tmp_path / "cli-out"
    exit_code = main(
        [str(sample_pdf), "-o", str(out_dir), "--size", "640x480", "--pages", "1-2"]
    )
    assert exit_code == 0
    files = sorted(out_dir.glob("*.jpg"))
    assert len(files) == 2
    with Image.open(files[0]) as image:
        assert image.size == (640, 480)


def test_cli_reports_missing_file(tmp_path, capsys):
    assert main([str(tmp_path / "missing.pdf"), "-o", str(tmp_path / "o")]) == 1
    assert "エラー" in capsys.readouterr().err
