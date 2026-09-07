"""PDF → JPG 変換のコマンドラインインターフェース."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pdf2jpg.converter import (
    DEFAULT_DPI,
    FIT_MODES,
    ConversionError,
    ConvertOptions,
    iter_convert_pdf,
    parse_pages,
    parse_size,
    pymupdf,
)

EPILOG = """\
使用例:
  pdf2jpg doc.pdf --size 1920x1080            # 16:9 に収めて出力 (余白は白)
  pdf2jpg doc.pdf --size 1080x --quality 95   # 幅1080px、高さは自動
  pdf2jpg doc.pdf --size 800x800 --fit cover  # 正方形に切り抜き
  pdf2jpg doc.pdf --dpi 300 --pages 1-3,7     # 300dpi で 1〜3,7 ページのみ
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pdf2jpg",
        description="PDF のページを任意のサイズの JPG 画像に変換します。",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("pdf", type=Path, nargs="+", help="変換する PDF ファイル")
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=Path("output"),
        help="出力先ディレクトリ (既定: output)",
    )
    parser.add_argument(
        "-s",
        "--size",
        help="出力サイズ。WIDTHxHEIGHT / WIDTHx / xHEIGHT (例: 1920x1080, 1080x)",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=DEFAULT_DPI,
        help=f"--size 未指定時の解像度 (既定: {DEFAULT_DPI})",
    )
    parser.add_argument(
        "--scale",
        type=float,
        help="--size 未指定時の倍率。指定すると --dpi より優先される",
    )
    parser.add_argument(
        "--fit",
        choices=FIT_MODES,
        default="contain",
        help="幅と高さを両方指定したときの合わせ方 (既定: contain)",
    )
    parser.add_argument(
        "--background",
        default="#ffffff",
        help="contain の余白色 (既定: #ffffff)",
    )
    parser.add_argument(
        "-q", "--quality", type=int, default=90, help="JPEG 品質 1〜100 (既定: 90)"
    )
    parser.add_argument(
        "-p", "--pages", help='変換するページ (例: "1,3-5,8-")。既定は全ページ'
    )
    parser.add_argument("--grayscale", action="store_true", help="グレースケールで出力")
    parser.add_argument("--quiet", action="store_true", help="進捗を表示しない")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    width = height = None
    if args.size:
        try:
            width, height = parse_size(args.size)
        except ValueError as exc:
            parser.error(str(exc))

    exit_code = 0
    for pdf_path in args.pdf:
        pages = None
        if args.pages:
            try:
                with pymupdf.open(pdf_path) as document:
                    pages = parse_pages(args.pages, document.page_count)
            except ValueError as exc:
                parser.error(str(exc))
            except Exception as exc:
                print(f"エラー: {pdf_path}: {exc}", file=sys.stderr)
                exit_code = 1
                continue

        try:
            options = ConvertOptions(
                width=width,
                height=height,
                dpi=args.dpi,
                scale=args.scale,
                fit=args.fit,
                background=args.background,
                quality=args.quality,
                pages=pages,
                grayscale=args.grayscale,
            )
        except ValueError as exc:
            parser.error(str(exc))

        try:
            count = 0
            for destination in iter_convert_pdf(pdf_path, args.output_dir, options):
                count += 1
                if not args.quiet:
                    print(destination)
            if not args.quiet:
                print(f"{pdf_path}: {count} ページを変換しました", file=sys.stderr)
        except ConversionError as exc:
            print(f"エラー: {exc}", file=sys.stderr)
            exit_code = 1

    return exit_code


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
