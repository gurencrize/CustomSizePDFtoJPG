"""GUI 入力（すべて文字列）から :class:`ConvertOptions` を組み立てる処理.

tkinter に依存しないので、GUI なしの環境でもテストできる。
"""

from __future__ import annotations

from dataclasses import dataclass

from PIL import ImageColor

from pdf2jpg.converter import ConvertOptions, parse_pages, parse_size

#: サイズの決め方
SIZE_MODES = ("pixels", "dpi", "scale")
#: ページ指定の構文チェックに使う仮のページ数
_SYNTAX_CHECK_PAGES = 1_000_000


@dataclass(frozen=True)
class FormResult:
    """フォームから得られた変換設定.

    ページ指定は PDF ごとにページ数が異なるため、文字列のまま保持して
    :func:`pages_for_document` で実ページ番号へ展開する。
    """

    options: ConvertOptions
    pages_spec: str = ""

    def pages_for_document(self, page_count: int) -> list[int] | None:
        if not self.pages_spec:
            return None
        return parse_pages(self.pages_spec, page_count)


class FormError(ValueError):
    """入力内容が不正な場合に送出される例外."""

    def __init__(self, message: str, field: str = "") -> None:
        super().__init__(message)
        self.field = field


def _to_int(text: str, field: str, label: str) -> int:
    try:
        return int(text.strip())
    except ValueError:
        raise FormError(f"{label}には整数を入力してください: {text!r}", field) from None


def _to_float(text: str, field: str, label: str) -> float:
    try:
        return float(text.strip())
    except ValueError:
        raise FormError(f"{label}には数値を入力してください: {text!r}", field) from None


def validate_pages(spec: str) -> str:
    """ページ指定の構文だけを検証し、正規化した文字列を返す."""
    spec = spec.strip()
    if not spec:
        return ""
    try:
        parse_pages(spec, _SYNTAX_CHECK_PAGES)
    except ValueError as exc:
        raise FormError(str(exc), "pages") from None
    return spec


def validate_background(color: str) -> str:
    """背景色として使える文字列かを検証する."""
    color = color.strip()
    if not color:
        raise FormError("背景色を入力してください。", "background")
    try:
        ImageColor.getrgb(color)
    except ValueError:
        raise FormError(f"背景色を解釈できません: {color!r}", "background") from None
    return color


def build_options(
    *,
    size_mode: str = "pixels",
    width: str = "",
    height: str = "",
    dpi: str = "150",
    scale: str = "1.0",
    fit: str = "contain",
    background: str = "#ffffff",
    quality: str = "90",
    pages: str = "",
    grayscale: bool = False,
) -> FormResult:
    """GUI のフォーム値から変換オプションを作る。

    不正な入力は :class:`FormError` として、どの項目が原因かを添えて返す。
    """
    if size_mode not in SIZE_MODES:
        raise FormError(f"サイズの指定方法が不正です: {size_mode!r}", "size_mode")

    width_px: int | None = None
    height_px: int | None = None
    dpi_value = 150
    scale_value: float | None = None

    if size_mode == "pixels":
        if not width.strip() and not height.strip():
            raise FormError("幅か高さの少なくとも一方を入力してください。", "width")
        if width.strip():
            width_px = _to_int(width, "width", "幅")
        if height.strip():
            height_px = _to_int(height, "height", "高さ")
    elif size_mode == "dpi":
        dpi_value = _to_int(dpi, "dpi", "解像度")
    else:
        scale_value = _to_float(scale, "scale", "倍率")

    quality_value = _to_int(quality, "quality", "品質")
    background_value = validate_background(background)
    pages_value = validate_pages(pages)

    try:
        options = ConvertOptions(
            width=width_px,
            height=height_px,
            dpi=dpi_value,
            scale=scale_value,
            fit=fit,
            background=background_value,
            quality=quality_value,
            grayscale=grayscale,
        )
    except ValueError as exc:
        raise FormError(str(exc)) from None

    return FormResult(options=options, pages_spec=pages_value)


def describe_size(options: ConvertOptions) -> str:
    """現在の設定を1行の説明文にする（GUI のプレビュー表示用）."""
    if options.width and options.height:
        return f"{options.width}x{options.height} px ({options.fit})"
    if options.width:
        return f"幅 {options.width} px（高さは比率維持）"
    if options.height:
        return f"高さ {options.height} px（幅は比率維持）"
    if options.scale:
        return f"元サイズの {options.scale:g} 倍"
    return f"{options.dpi} dpi"
