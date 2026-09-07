"""PDF を任意のサイズの JPG に変換するライブラリ."""

from pdf2jpg.converter import (
    ConversionError,
    ConvertOptions,
    convert_page,
    convert_pdf,
    iter_convert_pdf,
    parse_pages,
    parse_size,
)

__all__ = [
    "ConversionError",
    "ConvertOptions",
    "convert_page",
    "convert_pdf",
    "iter_convert_pdf",
    "parse_pages",
    "parse_size",
]
__version__ = "0.1.0"
