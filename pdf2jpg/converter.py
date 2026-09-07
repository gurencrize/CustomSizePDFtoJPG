"""PDFページを任意のサイズのJPGへ変換するコア処理."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Sequence

try:  # PyMuPDF 1.24.3 以降の正式なモジュール名
    import pymupdf
except ImportError:  # pragma: no cover - 古い PyMuPDF 用のフォールバック
    import fitz as pymupdf

from PIL import Image

#: fit未指定時に使う既定の解像度 (dpi)
DEFAULT_DPI = 150
#: 1ページあたりの最大ピクセル数 (メモリ暴走の防止)
MAX_PIXELS = 100_000_000

FIT_MODES = ("contain", "cover", "stretch")


class ConversionError(Exception):
    """変換に失敗した場合に送出される例外."""


@dataclass(frozen=True)
class ConvertOptions:
    """変換パラメータ.

    width / height はどちらか一方だけ指定すると、もう一方は元ページの
    アスペクト比から自動算出される。両方省略した場合は dpi (または scale)
    でページ本来のサイズを拡大縮小する。
    """

    width: int | None = None
    height: int | None = None
    dpi: int = DEFAULT_DPI
    scale: float | None = None
    fit: str = "contain"
    background: str = "#ffffff"
    quality: int = 90
    pages: Sequence[int] | None = None
    grayscale: bool = False

    def __post_init__(self) -> None:
        for name in ("width", "height"):
            value = getattr(self, name)
            if value is not None and value <= 0:
                raise ValueError(f"{name} は 1 以上で指定してください: {value}")
        if self.dpi <= 0:
            raise ValueError(f"dpi は 1 以上で指定してください: {self.dpi}")
        if self.scale is not None and self.scale <= 0:
            raise ValueError(f"scale は 0 より大きい値で指定してください: {self.scale}")
        if self.fit not in FIT_MODES:
            raise ValueError(f"fit は {FIT_MODES} のいずれかです: {self.fit}")
        if not 1 <= self.quality <= 100:
            raise ValueError(f"quality は 1〜100 で指定してください: {self.quality}")
        if self.width and self.height:
            if self.width * self.height > MAX_PIXELS:
                raise ValueError(
                    f"出力サイズが大きすぎます ({self.width}x{self.height})"
                )


def parse_pages(spec: str, page_count: int) -> list[int]:
    """"1,3-5,8-" 形式の指定を 0 始まりのページ番号リストへ変換する."""
    if not spec or not spec.strip():
        return list(range(page_count))

    selected: list[int] = []
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        m = re.fullmatch(r"(\d+)?\s*-\s*(\d+)?", chunk)
        if m:
            start = int(m.group(1)) if m.group(1) else 1
            end = int(m.group(2)) if m.group(2) else page_count
        elif chunk.isdigit():
            start = end = int(chunk)
        else:
            raise ValueError(f"ページ指定を解釈できません: {chunk!r}")

        if start < 1 or end < 1:
            raise ValueError(f"ページ番号は 1 以上です: {chunk!r}")
        if start > end:
            raise ValueError(f"ページ範囲の順序が不正です: {chunk!r}")
        for page in range(start, min(end, page_count) + 1):
            index = page - 1
            if index not in selected:
                selected.append(index)

    if not selected:
        raise ValueError(f"該当するページがありません: {spec!r}")
    return selected


def parse_size(spec: str) -> tuple[int | None, int | None]:
    """"1920x1080" / "1920x" / "x1080" 形式を (width, height) へ変換する."""
    text = spec.strip().lower().replace("×", "x")
    m = re.fullmatch(r"(\d+)?x(\d+)?", text)
    if not m or (m.group(1) is None and m.group(2) is None):
        raise ValueError(
            f"サイズ指定は WIDTHxHEIGHT 形式で指定してください: {spec!r}"
        )
    width = int(m.group(1)) if m.group(1) else None
    height = int(m.group(2)) if m.group(2) else None
    if width == 0 or height == 0:
        raise ValueError(f"サイズは 1 以上で指定してください: {spec!r}")
    return width, height


def _target_size(
    page_width: float, page_height: float, options: ConvertOptions
) -> tuple[int, int]:
    """1ページ分の出力ピクセルサイズを決める."""
    aspect = page_width / page_height if page_height else 1.0
    width, height = options.width, options.height

    if width and height:
        return width, height
    if width:
        return width, max(1, round(width / aspect))
    if height:
        return max(1, round(height * aspect)), height

    factor = options.scale if options.scale else options.dpi / 72.0
    return (
        max(1, round(page_width * factor)),
        max(1, round(page_height * factor)),
    )


def _render_page(page: "pymupdf.Page", target: tuple[int, int], options: ConvertOptions):
    """ページを目標サイズ以上の解像度でラスタライズして Image を返す."""
    target_w, target_h = target
    rect = page.rect
    if rect.width <= 0 or rect.height <= 0:
        raise ConversionError(f"ページサイズが不正です (page {page.number + 1})")

    # 縮小のみで済むよう、必要な倍率の大きい方に合わせてレンダリングする。
    factor = max(target_w / rect.width, target_h / rect.height)
    if factor * factor * rect.width * rect.height > MAX_PIXELS:
        factor = math.sqrt(MAX_PIXELS / (rect.width * rect.height))

    pixmap = page.get_pixmap(matrix=pymupdf.Matrix(factor, factor), alpha=False)
    return Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)


def _fit_image(image: Image.Image, target: tuple[int, int], options: ConvertOptions):
    """fit モードに従って画像を目標サイズへ整形する."""
    target_w, target_h = target
    if options.fit == "stretch":
        return image.resize((target_w, target_h), Image.LANCZOS)

    src_w, src_h = image.size
    if options.fit == "cover":
        ratio = max(target_w / src_w, target_h / src_h)
        resized = image.resize(
            (max(target_w, round(src_w * ratio)), max(target_h, round(src_h * ratio))),
            Image.LANCZOS,
        )
        left = (resized.width - target_w) // 2
        top = (resized.height - target_h) // 2
        return resized.crop((left, top, left + target_w, top + target_h))

    # contain: 余白を背景色で埋める
    ratio = min(target_w / src_w, target_h / src_h)
    resized = image.resize(
        (max(1, round(src_w * ratio)), max(1, round(src_h * ratio))), Image.LANCZOS
    )
    canvas = Image.new("RGB", (target_w, target_h), options.background)
    canvas.paste(
        resized,
        ((target_w - resized.width) // 2, (target_h - resized.height) // 2),
    )
    return canvas


def convert_page(page: "pymupdf.Page", options: ConvertOptions) -> Image.Image:
    """1ページを指定サイズの :class:`PIL.Image.Image` に変換する."""
    target = _target_size(page.rect.width, page.rect.height, options)
    image = _render_page(page, target, options)
    if image.size != target:
        image = _fit_image(image, target, options)
    if options.grayscale:
        image = image.convert("L")
    return image


def _output_path(output_dir: Path, stem: str, page_number: int, total: int) -> Path:
    digits = max(3, len(str(total)))
    return output_dir / f"{stem}_p{page_number:0{digits}d}.jpg"


def convert_pdf(
    pdf_path: str | Path,
    output_dir: str | Path,
    options: ConvertOptions | None = None,
    *,
    stem: str | None = None,
) -> list[Path]:
    """PDF を指定サイズの JPG 群へ変換し、生成したパスを返す."""
    return list(iter_convert_pdf(pdf_path, output_dir, options, stem=stem))


def iter_convert_pdf(
    pdf_path: str | Path,
    output_dir: str | Path,
    options: ConvertOptions | None = None,
    *,
    stem: str | None = None,
) -> Iterator[Path]:
    """:func:`convert_pdf` の逐次版。1ページ書き出すごとにパスを yield する."""
    options = options or ConvertOptions()
    pdf_path = Path(pdf_path)
    output_dir = Path(output_dir)

    if not pdf_path.is_file():
        raise ConversionError(f"PDF が見つかりません: {pdf_path}")

    try:
        document = pymupdf.open(pdf_path)
    except Exception as exc:  # pragma: no cover - PyMuPDF 依存のエラー
        raise ConversionError(f"PDF を開けません: {pdf_path} ({exc})") from exc

    with document:
        if document.needs_pass:
            raise ConversionError(f"パスワード保護された PDF です: {pdf_path}")
        if document.page_count == 0:
            raise ConversionError(f"ページがありません: {pdf_path}")

        indexes: Iterable[int] = (
            options.pages if options.pages is not None else range(document.page_count)
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        base = stem or pdf_path.stem

        for index in indexes:
            if not 0 <= index < document.page_count:
                raise ConversionError(
                    f"ページ {index + 1} は存在しません (全 {document.page_count} ページ)"
                )
            image = convert_page(document[index], options)
            destination = _output_path(
                output_dir, base, index + 1, document.page_count
            )
            image.save(
                destination,
                format="JPEG",
                quality=options.quality,
                optimize=True,
                progressive=True,
            )
            yield destination
